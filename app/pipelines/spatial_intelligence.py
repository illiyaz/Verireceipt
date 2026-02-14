"""
Spatial Intelligence Module for Document Understanding.

This module implements human-like document layout understanding using:
1. 2D spatial awareness (bounding boxes)
2. Semantic role classification (label vs entity)
3. Document zone detection (header, body, footer)
4. Relative positioning heuristics

The goal is to replicate how a human would read and understand a document
by considering visual layout, not just text sequence.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Semantic Role Classification
# =============================================================================

class SemanticRole(Enum):
    """Semantic role of a text element in a document."""
    LABEL = "label"           # Field label (e.g., "Bill To", "Invoice No")
    ENTITY = "entity"         # Named entity (e.g., "RGV Technologies Inc")
    VALUE = "value"           # Field value (e.g., "12345", "$100.00")
    HEADING = "heading"       # Section heading (e.g., "INVOICE", "PARTICULARS")
    BODY = "body"             # Body text (e.g., descriptions, notes)
    FOOTER = "footer"         # Footer text (e.g., "Thank you for your business")
    UNKNOWN = "unknown"


@dataclass
class SemanticToken:
    """A token with semantic role annotation."""
    text: str
    role: SemanticRole
    confidence: float
    x0: Optional[float] = None
    y0: Optional[float] = None
    x1: Optional[float] = None
    y1: Optional[float] = None
    line_idx: int = 0
    reasons: List[str] = field(default_factory=list)
    
    @property
    def has_coords(self) -> bool:
        return all(c is not None for c in [self.x0, self.y0, self.x1, self.y1])
    
    @property
    def center_x(self) -> Optional[float]:
        if self.x0 is not None and self.x1 is not None:
            return (self.x0 + self.x1) / 2
        return None
    
    @property
    def center_y(self) -> Optional[float]:
        if self.y0 is not None and self.y1 is not None:
            return (self.y0 + self.y1) / 2
        return None


# -----------------------------------------------------------------------------
# Label Patterns (things that are NOT entities)
# -----------------------------------------------------------------------------

# Labels that mark sections/fields
LABEL_PATTERNS = {
    # Billing/shipping labels
    "bill to", "billed to", "billing address", "billing info",
    "ship to", "shipped to", "shipping address", "deliver to", "delivery address",
    "sold to", "customer", "consignee", "buyer", "purchaser",
    "from", "seller", "vendor", "supplier", "shipper", "exporter", "importer",
    
    # Document metadata labels
    "invoice no", "invoice number", "invoice #", "inv no", "inv #",
    "receipt no", "receipt number", "order no", "order number", "po no",
    "date", "invoice date", "order date", "due date", "ship date",
    "reference", "ref no", "ref #", "account no", "account #",
    "terms", "payment terms", "due", "amount due",
    
    # Table headers
    "description", "particulars", "item", "items", "product", "service",
    "qty", "quantity", "unit", "units", "rate", "price", "unit price",
    "amount", "total", "subtotal", "sub total", "grand total", "net total",
    "tax", "vat", "gst", "cgst", "sgst", "igst", "hst", "sales tax",
    "discount", "shipping", "handling", "fee", "fees",
    
    # Contact labels
    "phone", "tel", "telephone", "fax", "email", "e-mail", "website", "web",
    "address", "contact", "contact us",
}

# Patterns that indicate a label (regex)
LABEL_REGEX_PATTERNS = [
    r"^[A-Z][a-z]+\s+[Tt]o:?$",  # "Bill To", "Ship To"
    r"^[A-Z]+\s+[A-Z]+:?$",       # "BILL TO", "INVOICE NO"
    r".*:\s*$",                    # Anything ending with colon
    r"^#\d+$",                     # "#123" reference numbers
    r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$",  # Dates
    r"^\d+\.\s*\w",               # Numbered list items: "1.", "2.", etc.
]

# Body text patterns (not entities)
BODY_TEXT_PATTERNS = [
    r"^\d+\.",                     # Starts with number and period (list item)
    r"\bterms\s*(and|&)\s*conditions\b",
    r"\blicense\b.*\b(valid|grant|non-exclusive|transferable)\b",
    r"\brestrictions?\s+on\b",
    r"\bpayment\s+(is\s+)?due\b",
    r"\blate\s+payments?\b",
    r"\bincur\s+a\s+fee\b",
    r"\bauthorized\s+signatory\b",
    r"\bcustomer\s+sign\b",
    r"\bthank\s+you\b",
    r"\bplease\s+(contact|call|visit)\b",
    r"\bif\s+you\s+have\b",
    r"\bfor\s+(any\s+)?queries\b",
]

# Address patterns (not entities)
ADDRESS_PATTERNS = [
    r"^\d+\s+\w+\s+(street|st\.?|avenue|ave\.?|road|rd\.?|blvd|boulevard|lane|ln\.?|drive|dr\.?|way|court|ct\.?|place|pl\.?|circle|cir\.?|viaduct|trail|parkway|pkwy)",
    r"\b(street|avenue|road|blvd|lane|drive|way|court|place|circle|viaduct|trail|parkway)\s*,",
    r",\s*(tx|ca|ny|fl|il|pa|oh|ga|nc|mi|nj|va|wa|az|ma|tn|in|mo|md|wi|mn|co|al|sc|la|ky|or|ok|ct|ut|ia|nv|ar|ms|ks|nm|ne|wv|id|hi|nh|me|mt|ri|de|sd|nd|ak|vt|wy|dc)\s*[-\s]?\d{5}",
    r"\b\d{5}(-\d{4})?\b",  # ZIP code
    r"^address[-:\s]",
    r",\s*(texas|california|new york|florida|illinois|pennsylvania|ohio|georgia)",
]

# Entity indicators (things that ARE likely entities)
ENTITY_INDICATORS = {
    # Legal suffixes
    "inc", "inc.", "llc", "ltd", "ltd.", "corp", "corp.", "corporation",
    "company", "co.", "co,", "pvt", "private", "limited",
    "gmbh", "sa", "s.a.", "srl", "s.r.l.", "pty", "bv", "b.v.",
    "oy", "kk", "k.k.", "ag", "a.g.", "nv", "n.v.", "plc", "p.l.c.",
    "llp", "l.l.p.", "lp", "l.p.", "pllc", "pc", "p.c.",
    
    # Industry terms often in company names
    "technologies", "technology", "tech", "systems", "solutions",
    "services", "consulting", "group", "holdings", "enterprises",
    "industries", "international", "global", "motors", "foods",
    "electronics", "software", "hardware", "networks", "media",
}


def classify_semantic_role(
    text: str,
    context_before: Optional[str] = None,
    context_after: Optional[str] = None,
    is_uppercase: bool = False,
    has_colon: bool = False,
    position_hint: str = "middle",  # "top", "middle", "bottom"
) -> Tuple[SemanticRole, float, List[str]]:
    """
    Classify the semantic role of a text element.
    
    This mimics how a human would classify text:
    - Labels are typically short, end with colons, or are known field names
    - Entities are proper nouns with legal suffixes or specific patterns
    - Values are numbers, dates, or follow labels
    
    Args:
        text: The text to classify
        context_before: Text on previous line
        context_after: Text on next line
        is_uppercase: Whether text is all uppercase
        has_colon: Whether text ends with or contains colon
        position_hint: Position in document ("top", "middle", "bottom")
    
    Returns:
        Tuple of (role, confidence, reasons)
    """
    if not text or not text.strip():
        return SemanticRole.UNKNOWN, 0.0, ["empty_text"]
    
    t = text.strip()
    t_lower = t.lower()
    t_clean = re.sub(r'[:\s]+$', '', t_lower)
    reasons = []
    
    # ==========================================================================
    # LABEL Detection (high priority)
    # ==========================================================================
    
    label_score = 0.0
    
    # Exact match with known labels
    if t_clean in LABEL_PATTERNS:
        label_score += 0.8
        reasons.append(f"exact_label_match:{t_clean}")
    
    # Starts with known label
    for label in LABEL_PATTERNS:
        if t_clean.startswith(label) and len(t_clean) <= len(label) + 5:
            label_score += 0.6
            reasons.append(f"starts_with_label:{label}")
            break
    
    # Ends with colon (strong label indicator)
    if t.rstrip().endswith(':'):
        label_score += 0.4
        reasons.append("ends_with_colon")
    
    # Matches label regex patterns
    for pattern in LABEL_REGEX_PATTERNS:
        if re.match(pattern, t, re.IGNORECASE):
            label_score += 0.3
            reasons.append(f"regex_pattern:{pattern[:20]}")
            break
    
    # Short uppercase text (2-3 words) often a label or heading
    words = t.split()
    if is_uppercase and len(words) <= 3 and len(t) <= 25:
        # But check if it looks like a company name first
        if not any(ind in t_lower for ind in ENTITY_INDICATORS):
            label_score += 0.3
            reasons.append("short_uppercase")
    
    # ==========================================================================
    # BODY TEXT Detection (reject before entity classification)
    # ==========================================================================
    
    body_score = 0.0
    
    for pattern in BODY_TEXT_PATTERNS:
        if re.search(pattern, t_lower):
            body_score += 0.6
            reasons.append(f"body_text_pattern:{pattern[:20]}")
            break
    
    # If strong body text signal, return early
    if body_score >= 0.6:
        return SemanticRole.BODY, body_score, reasons
    
    # ==========================================================================
    # ADDRESS Detection (reject before entity classification)
    # ==========================================================================
    
    address_score = 0.0
    
    for pattern in ADDRESS_PATTERNS:
        if re.search(pattern, t_lower, re.IGNORECASE):
            address_score += 0.7
            reasons.append(f"address_pattern:{pattern[:25]}")
            break
    
    # If strong address signal, return as VALUE (addresses are values, not entities)
    if address_score >= 0.7:
        return SemanticRole.VALUE, address_score, reasons
    
    # ==========================================================================
    # ENTITY Detection
    # ==========================================================================
    
    entity_score = 0.0
    
    # Has legal suffix (very strong entity indicator)
    for suffix in ENTITY_INDICATORS:
        if t_lower.endswith(suffix) or f" {suffix}" in t_lower:
            entity_score += 0.7
            reasons.append(f"legal_suffix:{suffix}")
            break
    
    # Title case with multiple words (common for company names)
    if len(words) >= 2 and t[0].isupper():
        # Check if it's title case or proper capitalization
        title_case_words = sum(1 for w in words if w[0].isupper() if len(w) > 0)
        if title_case_words >= len(words) * 0.6:
            entity_score += 0.3
            reasons.append("title_case_multiword")
    
    # ALL CAPS with 2+ words and no colon (often company names in headers)
    if is_uppercase and len(words) >= 2 and ':' not in t:
        entity_score += 0.2
        reasons.append("allcaps_multiword")
    
    # Followed by address (strong entity indicator)
    if context_after:
        ctx_lower = context_after.lower()
        if any(addr in ctx_lower for addr in ["address", "street", "road", "avenue", "blvd", "phone", "tel", "email"]):
            entity_score += 0.4
            reasons.append("followed_by_contact")
    
    # At top of document and looks substantial
    if position_hint == "top" and len(t) > 5 and not t.rstrip().endswith(':'):
        entity_score += 0.2
        reasons.append("top_position")
    
    # ==========================================================================
    # VALUE Detection
    # ==========================================================================
    
    value_score = 0.0
    
    # Mostly numeric
    digit_ratio = sum(c.isdigit() for c in t) / max(len(t), 1)
    if digit_ratio > 0.5:
        value_score += 0.6
        reasons.append(f"numeric_ratio:{digit_ratio:.2f}")
    
    # Currency pattern
    if re.search(r'[\$€£¥₹]\s*[\d,]+\.?\d*', t) or re.search(r'[\d,]+\.?\d*\s*[\$€£¥₹]', t):
        value_score += 0.7
        reasons.append("currency_pattern")
    
    # Date pattern
    if re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', t):
        value_score += 0.6
        reasons.append("date_pattern")
    
    # Preceded by a label
    if context_before:
        ctx_clean = re.sub(r'[:\s]+$', '', context_before.lower())
        if ctx_clean in LABEL_PATTERNS:
            value_score += 0.4
            reasons.append("preceded_by_label")
    
    # ==========================================================================
    # HEADING Detection
    # ==========================================================================
    
    heading_score = 0.0
    
    # Document type words
    doc_types = {"invoice", "receipt", "bill", "statement", "quotation", "order", "estimate"}
    if t_clean in doc_types:
        heading_score += 0.7
        reasons.append("document_type_heading")
    
    # Section headings
    section_words = {"particulars", "items", "description", "details", "summary", "notes"}
    if t_clean in section_words:
        heading_score += 0.5
        reasons.append("section_heading")
    
    # ==========================================================================
    # FOOTER Detection
    # ==========================================================================
    
    footer_score = 0.0
    
    # Common footer phrases
    footer_phrases = [
        "thank you", "thanks for", "please ", "if you have",
        "contact us", "for any queries", "terms and conditions",
        "this is computer generated", "does not require signature",
        "e. & o.e.", "errors and omissions",
    ]
    for phrase in footer_phrases:
        if phrase in t_lower:
            footer_score += 0.7
            reasons.append(f"footer_phrase:{phrase}")
            break
    
    if position_hint == "bottom":
        footer_score += 0.2
        reasons.append("bottom_position")
    
    # ==========================================================================
    # Final Classification
    # ==========================================================================
    
    scores = {
        SemanticRole.LABEL: label_score,
        SemanticRole.ENTITY: entity_score,
        SemanticRole.VALUE: value_score,
        SemanticRole.HEADING: heading_score,
        SemanticRole.FOOTER: footer_score,
    }
    
    best_role = max(scores, key=scores.get)
    best_score = scores[best_role]
    
    # Require minimum confidence
    if best_score < 0.3:
        return SemanticRole.UNKNOWN, best_score, reasons
    
    return best_role, best_score, reasons


# =============================================================================
# 2D Spatial Analysis
# =============================================================================

@dataclass
class SpatialRegion:
    """A region in 2D space with semantic meaning."""
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    role: str  # "seller", "buyer", "items", "totals", "header", "footer"
    confidence: float = 1.0
    anchor_text: Optional[str] = None


@dataclass
class SpatialAnalysis:
    """Result of spatial document analysis."""
    regions: List[SpatialRegion]
    seller_region: Optional[SpatialRegion] = None
    buyer_region: Optional[SpatialRegion] = None
    items_region: Optional[SpatialRegion] = None
    totals_region: Optional[SpatialRegion] = None
    header_region: Optional[SpatialRegion] = None
    page_width: float = 0
    page_height: float = 0
    layout_type: str = "unknown"  # "single_column", "two_column", "complex"
    evidence: Dict[str, Any] = field(default_factory=dict)


def analyze_spatial_layout(
    tokens: List[Any],  # LayoutToken list
    page_width: float = 612,  # Default letter size
    page_height: float = 792,
) -> SpatialAnalysis:
    """
    Analyze the 2D spatial layout of a document.
    
    This function:
    1. Detects document regions (seller, buyer, items, totals)
    2. Classifies layout type (single column, two column, etc.)
    3. Identifies anchor texts that define regions
    
    Args:
        tokens: List of LayoutTokens with coordinates
        page_width: Page width in points
        page_height: Page height in points
    
    Returns:
        SpatialAnalysis with detected regions
    """
    analysis = SpatialAnalysis(
        regions=[],
        page_width=page_width,
        page_height=page_height,
        evidence={}
    )
    
    if not tokens:
        return analysis
    
    # Collect tokens with coordinates
    coord_tokens = [t for t in tokens if hasattr(t, 'has_coords') and t.has_coords]
    
    if not coord_tokens:
        # Fallback to line-based analysis
        analysis.layout_type = "line_based_fallback"
        return _analyze_line_based(tokens, analysis)
    
    # ==========================================================================
    # Step 1: Detect anchor texts and their positions
    # ==========================================================================
    
    seller_anchors = {"from", "sold by", "vendor", "supplier", "seller", "shipper", "exporter"}
    buyer_anchors = {"bill to", "billed to", "ship to", "sold to", "customer", "buyer", "consignee"}
    item_anchors = {"particulars", "description", "items", "qty", "quantity", "details"}
    total_anchors = {"total", "grand total", "subtotal", "amount due", "balance due"}
    
    anchor_positions = {
        "seller": [],
        "buyer": [],
        "items": [],
        "totals": [],
    }
    
    for token in coord_tokens:
        text_lower = token.text.lower().strip()
        text_clean = re.sub(r'[:\s]+$', '', text_lower)
        
        if text_clean in seller_anchors:
            anchor_positions["seller"].append((token, text_clean))
        elif text_clean in buyer_anchors:
            anchor_positions["buyer"].append((token, text_clean))
        elif text_clean in item_anchors:
            anchor_positions["items"].append((token, text_clean))
        elif text_clean in total_anchors:
            anchor_positions["totals"].append((token, text_clean))
    
    analysis.evidence["anchor_positions"] = {
        k: [(t.text, t.line_idx, t.y0) for t, _ in v] 
        for k, v in anchor_positions.items()
    }
    
    # ==========================================================================
    # Step 2: Detect layout type based on x-coordinate distribution
    # ==========================================================================
    
    x_coords = [t.center_x for t in coord_tokens if t.center_x is not None]
    if x_coords:
        x_min, x_max = min(x_coords), max(x_coords)
        x_range = x_max - x_min
        
        # Check for two-column layout
        mid_x = (x_min + x_max) / 2
        left_tokens = sum(1 for x in x_coords if x < mid_x - x_range * 0.1)
        right_tokens = sum(1 for x in x_coords if x > mid_x + x_range * 0.1)
        
        if left_tokens > 5 and right_tokens > 5:
            ratio = min(left_tokens, right_tokens) / max(left_tokens, right_tokens)
            if ratio > 0.3:
                analysis.layout_type = "two_column"
            else:
                analysis.layout_type = "single_column"
        else:
            analysis.layout_type = "single_column"
        
        analysis.evidence["layout_detection"] = {
            "x_range": x_range,
            "left_tokens": left_tokens,
            "right_tokens": right_tokens,
            "layout_type": analysis.layout_type,
        }
    
    # ==========================================================================
    # Step 3: Define regions based on anchors and spatial analysis
    # ==========================================================================
    
    # Header region (top 20% of page)
    header_y_max = page_height * 0.20
    header_tokens = [t for t in coord_tokens if t.y0 is not None and t.y0 < header_y_max]
    if header_tokens:
        analysis.header_region = SpatialRegion(
            name="header",
            x0=min(t.x0 for t in header_tokens if t.x0),
            y0=0,
            x1=max(t.x1 for t in header_tokens if t.x1),
            y1=header_y_max,
            role="header",
            confidence=0.9,
        )
        analysis.regions.append(analysis.header_region)
    
    # Seller region (usually top-left or top area, near "From" or company name)
    if anchor_positions["seller"]:
        anchor_token, anchor_text = anchor_positions["seller"][0]
        # Region extends from anchor down ~100 points and right ~200 points
        analysis.seller_region = SpatialRegion(
            name="seller",
            x0=anchor_token.x0 if anchor_token.x0 else 0,
            y0=anchor_token.y0 if anchor_token.y0 else 0,
            x1=min((anchor_token.x0 or 0) + 250, page_width),
            y1=min((anchor_token.y0 or 0) + 120, page_height),
            role="seller",
            confidence=0.85,
            anchor_text=anchor_text,
        )
        analysis.regions.append(analysis.seller_region)
    
    # Buyer region (near "Bill To" / "Ship To" anchor)
    if anchor_positions["buyer"]:
        anchor_token, anchor_text = anchor_positions["buyer"][0]
        analysis.buyer_region = SpatialRegion(
            name="buyer",
            x0=anchor_token.x0 if anchor_token.x0 else 0,
            y0=anchor_token.y0 if anchor_token.y0 else 0,
            x1=min((anchor_token.x0 or 0) + 250, page_width),
            y1=min((anchor_token.y0 or 0) + 120, page_height),
            role="buyer",
            confidence=0.9,
            anchor_text=anchor_text,
        )
        analysis.regions.append(analysis.buyer_region)
    
    # Totals region (near "Total" anchor, usually bottom right)
    if anchor_positions["totals"]:
        anchor_token, anchor_text = anchor_positions["totals"][-1]  # Use last (lowest) total
        analysis.totals_region = SpatialRegion(
            name="totals",
            x0=max((anchor_token.x0 or 0) - 100, 0),
            y0=max((anchor_token.y0 or 0) - 50, 0),
            x1=page_width,
            y1=min((anchor_token.y0 or 0) + 100, page_height),
            role="totals",
            confidence=0.85,
            anchor_text=anchor_text,
        )
        analysis.regions.append(analysis.totals_region)
    
    return analysis


def _analyze_line_based(tokens: List[Any], analysis: SpatialAnalysis) -> SpatialAnalysis:
    """Fallback analysis when coordinates are not available."""
    # Use line indices to estimate regions
    max_line = max((t.line_idx for t in tokens), default=0)
    
    if max_line > 0:
        # Header = first 20% of lines
        header_max = int(max_line * 0.2)
        # Footer = last 10% of lines
        footer_min = int(max_line * 0.9)
        
        analysis.evidence["line_based"] = {
            "max_line": max_line,
            "header_max_line": header_max,
            "footer_min_line": footer_min,
        }
    
    return analysis


def is_token_in_region(
    token: Any,
    region: SpatialRegion,
    tolerance: float = 10.0
) -> bool:
    """Check if a token falls within a spatial region."""
    if not hasattr(token, 'has_coords') or not token.has_coords:
        return False
    
    return (
        token.x0 >= region.x0 - tolerance and
        token.x1 <= region.x1 + tolerance and
        token.y0 >= region.y0 - tolerance and
        token.y1 <= region.y1 + tolerance
    )


# =============================================================================
# Enhanced Merchant Extraction
# =============================================================================

@dataclass
class MerchantCandidate:
    """A candidate merchant with comprehensive scoring."""
    text: str
    score: float = 0.0
    semantic_role: SemanticRole = SemanticRole.UNKNOWN
    semantic_confidence: float = 0.0
    in_seller_region: bool = False
    in_buyer_region: bool = False
    in_header_region: bool = False
    has_legal_suffix: bool = False
    has_contact_nearby: bool = False
    position_score: float = 0.0
    line_idx: int = 0
    x0: Optional[float] = None
    y0: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    boosts: List[Dict[str, Any]] = field(default_factory=list)
    penalties: List[Dict[str, Any]] = field(default_factory=list)


def extract_merchant_with_spatial_intelligence(
    tokens: List[Any],
    page_width: float = 612,
    page_height: float = 792,
    debug: bool = False,
) -> Tuple[Optional[str], List[MerchantCandidate], Dict[str, Any]]:
    """
    Extract merchant using spatial intelligence and semantic role classification.
    
    This implements human-like document understanding:
    1. Analyze 2D layout to find seller/buyer regions
    2. Classify each text element's semantic role
    3. Score candidates based on spatial + semantic signals
    4. Return the most likely merchant
    
    Args:
        tokens: List of LayoutTokens
        page_width: Page width for spatial analysis
        page_height: Page height for spatial analysis
        debug: If True, include detailed debug info
    
    Returns:
        Tuple of (merchant_text, all_candidates, evidence_dict)
    """
    evidence = {
        "method": "spatial_intelligence",
        "token_count": len(tokens),
        "spatial_analysis": {},
        "semantic_analysis": {},
        "candidates": [],
    }
    
    if not tokens:
        return None, [], evidence
    
    # Step 1: Spatial layout analysis
    spatial = analyze_spatial_layout(tokens, page_width, page_height)
    evidence["spatial_analysis"] = {
        "layout_type": spatial.layout_type,
        "has_seller_region": spatial.seller_region is not None,
        "has_buyer_region": spatial.buyer_region is not None,
        "regions": [r.name for r in spatial.regions],
    }
    
    # Step 2: Build lines for context
    lines_dict: Dict[int, str] = {}
    for t in tokens:
        if t.line_idx not in lines_dict:
            lines_dict[t.line_idx] = t.text
        else:
            lines_dict[t.line_idx] += " " + t.text
    max_line = max(lines_dict.keys()) if lines_dict else 0
    
    # Step 3: Score each token as potential merchant
    candidates: List[MerchantCandidate] = []
    
    for token in tokens:
        text = token.text.strip()
        if len(text) < 3:
            continue
        
        # Get context
        context_before = lines_dict.get(token.line_idx - 1, "")
        context_after = lines_dict.get(token.line_idx + 1, "")
        
        # Determine position hint
        position_hint = "middle"
        if token.line_idx <= max_line * 0.2:
            position_hint = "top"
        elif token.line_idx >= max_line * 0.8:
            position_hint = "bottom"
        
        # Classify semantic role
        role, role_conf, role_reasons = classify_semantic_role(
            text,
            context_before=context_before,
            context_after=context_after,
            is_uppercase=text.isupper(),
            has_colon=':' in text,
            position_hint=position_hint,
        )
        
        # Skip labels, values, footers, body text - they're not merchants
        if role in (SemanticRole.LABEL, SemanticRole.VALUE, SemanticRole.FOOTER, SemanticRole.BODY):
            continue
        
        # Skip headings that are document types
        if role == SemanticRole.HEADING:
            doc_types = {"invoice", "receipt", "bill", "statement", "quotation"}
            if text.lower().strip() in doc_types:
                continue
        
        # Create candidate
        candidate = MerchantCandidate(
            text=text,
            semantic_role=role,
            semantic_confidence=role_conf,
            line_idx=token.line_idx,
            x0=token.x0 if hasattr(token, 'x0') else None,
            y0=token.y0 if hasattr(token, 'y0') else None,
            reasons=role_reasons.copy(),
        )
        
        # =======================================================================
        # Spatial Scoring
        # =======================================================================
        
        # Check region membership
        if spatial.seller_region and is_token_in_region(token, spatial.seller_region):
            candidate.in_seller_region = True
            candidate.score += 10
            candidate.boosts.append({"name": "seller_region", "delta": 10})
            candidate.reasons.append("in_seller_region")
        
        if spatial.buyer_region and is_token_in_region(token, spatial.buyer_region):
            candidate.in_buyer_region = True
            candidate.score -= 15  # Strong penalty for buyer region
            candidate.penalties.append({"name": "buyer_region", "delta": -15})
            candidate.reasons.append("in_buyer_region")
        
        if spatial.header_region and is_token_in_region(token, spatial.header_region):
            candidate.in_header_region = True
            candidate.score += 3
            candidate.boosts.append({"name": "header_region", "delta": 3})
            candidate.reasons.append("in_header_region")
        
        # Position-based scoring
        if position_hint == "top":
            candidate.position_score = 3
            candidate.score += 3
            candidate.boosts.append({"name": "top_position", "delta": 3})
        elif position_hint == "bottom":
            candidate.position_score = -2
            candidate.score -= 2
            candidate.penalties.append({"name": "bottom_position", "delta": -2})
        
        # =======================================================================
        # Semantic Scoring
        # =======================================================================
        
        # Entity role boost
        if role == SemanticRole.ENTITY:
            candidate.score += 5 * role_conf
            candidate.boosts.append({"name": "entity_role", "delta": 5 * role_conf})
        
        # Legal suffix detection
        text_lower = text.lower()
        for suffix in ENTITY_INDICATORS:
            if text_lower.endswith(suffix) or f" {suffix}" in text_lower:
                candidate.has_legal_suffix = True
                candidate.score += 8
                candidate.boosts.append({"name": "legal_suffix", "delta": 8})
                candidate.reasons.append(f"has_legal_suffix:{suffix}")
                break
        
        # Contact info nearby
        if context_after:
            ctx_lower = context_after.lower()
            if any(ind in ctx_lower for ind in ["address", "phone", "tel", "email", "fax"]):
                candidate.has_contact_nearby = True
                candidate.score += 5
                candidate.boosts.append({"name": "contact_nearby", "delta": 5})
                candidate.reasons.append("contact_info_nearby")
        
        # ALL CAPS multiword (common for company names in headers)
        words = text.split()
        if text.isupper() and len(words) >= 2 and ':' not in text:
            candidate.score += 2
            candidate.boosts.append({"name": "uppercase_multiword", "delta": 2})
            candidate.reasons.append("uppercase_multiword")
        
        # =======================================================================
        # Penalties
        # =======================================================================
        
        # Too short
        if len(text) < 5:
            candidate.score -= 3
            candidate.penalties.append({"name": "too_short", "delta": -3})
        
        # Has colon (likely a label)
        if ':' in text:
            candidate.score -= 5
            candidate.penalties.append({"name": "has_colon", "delta": -5})
        
        # Looks like address
        if re.search(r'\d+\s+\w+\s+(street|st|avenue|ave|road|rd)', text.lower()):
            candidate.score -= 5
            candidate.penalties.append({"name": "address_like", "delta": -5})
        
        # Mostly numeric
        digit_ratio = sum(c.isdigit() for c in text) / max(len(text), 1)
        if digit_ratio > 0.3:
            candidate.score -= 5
            candidate.penalties.append({"name": "numeric_heavy", "delta": -5})
        
        candidates.append(candidate)
    
    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)
    
    # Build evidence
    evidence["candidates"] = [
        {
            "text": c.text,
            "score": c.score,
            "role": c.semantic_role.value,
            "role_confidence": c.semantic_confidence,
            "in_seller_region": c.in_seller_region,
            "in_buyer_region": c.in_buyer_region,
            "reasons": c.reasons,
        }
        for c in candidates[:10]
    ]
    
    # Select winner
    if not candidates:
        return None, [], evidence
    
    winner = candidates[0]
    
    # Confidence check: if winner is in buyer region, be suspicious
    if winner.in_buyer_region and len(candidates) > 1:
        # Try to find a better candidate not in buyer region
        for c in candidates[1:]:
            if not c.in_buyer_region and c.score > 0:
                evidence["winner_override"] = {
                    "original": winner.text,
                    "reason": "original_in_buyer_region",
                    "replacement": c.text,
                }
                winner = c
                break
    
    return winner.text, candidates, evidence


# =============================================================================
# Integration Helper
# =============================================================================

def enhance_merchant_extraction(
    tokens: List[Any],
    current_merchant: Optional[str] = None,
    page_width: float = 612,
    page_height: float = 792,
) -> Dict[str, Any]:
    """
    Enhance existing merchant extraction with spatial intelligence.
    
    This can be used as a second-pass verification or tie-breaker.
    
    Args:
        tokens: LayoutTokens
        current_merchant: Currently extracted merchant (for comparison)
        page_width: Page width
        page_height: Page height
    
    Returns:
        Dict with enhanced extraction results and comparison
    """
    new_merchant, candidates, evidence = extract_merchant_with_spatial_intelligence(
        tokens, page_width, page_height
    )
    
    result = {
        "spatial_merchant": new_merchant,
        "current_merchant": current_merchant,
        "agreement": new_merchant == current_merchant if current_merchant else None,
        "candidates": evidence.get("candidates", []),
        "spatial_analysis": evidence.get("spatial_analysis", {}),
        "recommendation": None,
    }
    
    # Provide recommendation
    if current_merchant is None and new_merchant:
        result["recommendation"] = "use_spatial"
    elif current_merchant and new_merchant and current_merchant != new_merchant:
        # Check if spatial found a better candidate
        current_in_candidates = any(
            c["text"] == current_merchant for c in result["candidates"]
        )
        if current_in_candidates:
            current_score = next(
                c["score"] for c in result["candidates"] if c["text"] == current_merchant
            )
            new_score = result["candidates"][0]["score"] if result["candidates"] else 0
            if new_score > current_score + 5:
                result["recommendation"] = "use_spatial"
            else:
                result["recommendation"] = "keep_current"
        else:
            result["recommendation"] = "use_spatial"
    else:
        result["recommendation"] = "keep_current"
    
    return result


# =============================================================================
# Spatial Amount Extraction
# =============================================================================

@dataclass
class AmountCandidate:
    """A candidate amount value with context."""
    value: float
    raw_text: str
    label: Optional[str] = None  # Associated label (e.g., "Total", "Subtotal")
    label_distance: float = 0.0  # Distance from label
    line_idx: int = 0
    x0: Optional[float] = None
    y0: Optional[float] = None
    confidence: float = 0.0
    amount_type: str = "unknown"  # "total", "subtotal", "tax", "item", "unknown"
    reasons: List[str] = field(default_factory=list)


# Amount label patterns
TOTAL_LABELS = {
    "total", "grand total", "total amount", "amount due", "balance due",
    "total due", "net total", "final total", "pay this amount", "you owe",
    "amount payable", "total payable", "amount",  # Added "amount" as fallback
}

SUBTOTAL_LABELS = {
    "subtotal", "sub total", "sub-total", "net amount", "amount before tax",
    "taxable amount", "goods total", "items total", "merchandise total",
}

TAX_LABELS = {
    "tax", "taxes", "vat", "gst", "sales tax", "service tax", "cgst", "sgst", "igst",
    "hst", "pst", "qst", "tax amount", "total tax", "tax total", "tax value",
}

DISCOUNT_LABELS = {
    "discount", "savings", "promo", "coupon", "rebate", "adjustment",
}


def normalize_spaced_text(text: str) -> str:
    """
    Normalize text with excessive spacing (e.g., 'A m o u n t' -> 'Amount').
    
    This handles PDFs where text has been spaced out for formatting.
    """
    if not text:
        return text
    
    # Check if this looks like spaced-out text (alternating chars and spaces)
    words = text.split()
    
    # If most "words" are single characters, it's likely spaced-out text
    single_char_count = sum(1 for w in words if len(w) == 1)
    if len(words) > 2 and single_char_count > len(words) * 0.5:
        # Join single chars together
        result = []
        current_word = []
        for word in words:
            if len(word) == 1:
                current_word.append(word)
            else:
                if current_word:
                    result.append(''.join(current_word))
                    current_word = []
                result.append(word)
        if current_word:
            result.append(''.join(current_word))
        return ' '.join(result)
    
    return text

# Currency patterns
CURRENCY_PATTERN = re.compile(
    r'(?:[\$€£¥₹]|rs\.?|inr|usd|eur|gbp|cad|aud)?\s*'
    r'([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)'
    r'\s*(?:[\$€£¥₹]|rs\.?|inr|usd|eur|gbp|cad|aud)?',
    re.IGNORECASE
)


def extract_amount_from_text(text: str) -> Optional[float]:
    """Extract numeric amount from text."""
    if not text:
        return None
    
    # Remove currency symbols and clean
    clean = re.sub(r'[^\d,.\-]', ' ', text)
    clean = clean.strip()
    
    # Find number patterns
    matches = re.findall(r'[\d,]+\.?\d*', clean)
    if not matches:
        return None
    
    # Take the largest/most significant number
    amounts = []
    for m in matches:
        try:
            # Remove commas
            num_str = m.replace(',', '')
            if num_str:
                amounts.append(float(num_str))
        except ValueError:
            continue
    
    return max(amounts) if amounts else None


def find_label_for_amount(
    amount_token: Any,
    all_tokens: List[Any],
    label_set: Set[str],
) -> Tuple[Optional[str], float]:
    """
    Find a label associated with an amount token.
    
    Looks for labels:
    1. On the same line (to the left)
    2. On the line above
    3. In the same row (similar y-coordinate)
    4. Within ±3 lines (for column layouts where labels and amounts are on different rows)
    
    Returns:
        Tuple of (label_text, distance)
    """
    if not hasattr(amount_token, 'line_idx'):
        return None, float('inf')
    
    amount_line = amount_token.line_idx
    amount_y = amount_token.center_y if hasattr(amount_token, 'center_y') else None
    amount_x = amount_token.x0 if hasattr(amount_token, 'x0') else None
    
    best_label = None
    best_distance = float('inf')
    
    for token in all_tokens:
        text_lower = token.text.lower().strip()
        text_clean = re.sub(r'[:\s]+$', '', text_lower)
        
        # Also try normalizing spaced-out text
        text_normalized = normalize_spaced_text(text_clean).lower()
        
        if text_clean not in label_set and text_normalized not in label_set:
            continue
        
        # Calculate distance
        distance = float('inf')
        
        # Same line - check if label is to the left
        if token.line_idx == amount_line:
            if amount_x and hasattr(token, 'x1') and token.x1:
                if token.x1 < amount_x:  # Label is to the left
                    distance = amount_x - token.x1
        
        # Line above
        elif token.line_idx == amount_line - 1:
            distance = 50  # Default distance for adjacent line
            if amount_y and hasattr(token, 'center_y') and token.center_y:
                distance = abs(amount_y - token.center_y)
        
        # Label 1-3 lines BEFORE amount (amount comes after label)
        elif 1 <= (amount_line - token.line_idx) <= 3:
            line_diff = amount_line - token.line_idx
            distance = 60 + line_diff * 20  # Base distance + penalty per line
        
        # Label 1-3 lines AFTER amount (label comes after amount - common in some layouts)
        elif 1 <= (token.line_idx - amount_line) <= 3:
            line_diff = token.line_idx - amount_line
            distance = 70 + line_diff * 25  # Slightly higher penalty for labels after amounts
        
        # Same row (similar y-coordinate) - for column layouts
        elif amount_y and hasattr(token, 'center_y') and token.center_y:
            y_diff = abs(amount_y - token.center_y)
            if y_diff < 15:  # Within 15 points vertically
                if amount_x and hasattr(token, 'x1') and token.x1:
                    if token.x1 < amount_x:
                        distance = amount_x - token.x1
        
        if distance < best_distance:
            best_distance = distance
            best_label = token.text.strip()
    
    return best_label, best_distance


def extract_amounts_with_spatial_intelligence(
    tokens: List[Any],
    page_width: float = 612,
    page_height: float = 792,
) -> Dict[str, Any]:
    """
    Extract amounts (total, subtotal, tax) using spatial intelligence.
    
    This implements human-like amount detection:
    1. Find all numeric values in the document
    2. Associate each with its label based on spatial proximity
    3. Classify amounts as total/subtotal/tax based on labels and position
    4. Validate using mathematical relationships
    
    Args:
        tokens: List of LayoutTokens
        page_width: Page width
        page_height: Page height
    
    Returns:
        Dict with extracted amounts and evidence
    """
    result = {
        "total": None,
        "subtotal": None,
        "tax": None,
        "tax_rate": None,
        "discount": None,
        "confidence": 0.0,
        "method": "spatial_intelligence",
        "candidates": [],
        "validation": {},
        "evidence": {},
    }
    
    if not tokens:
        return result
    
    # Step 1: Find all amount candidates
    amount_candidates: List[AmountCandidate] = []
    
    for token in tokens:
        text = token.text.strip()
        
        # Skip very short or empty
        if len(text) < 2:
            continue
        
        # Check if contains a number
        amount = extract_amount_from_text(text)
        if amount is None or amount <= 0:
            continue
        
        # Skip if it looks like a date, phone, or reference number
        if re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', text):  # Date
            continue
        if re.search(r'\+?\d{10,}', text.replace(' ', '').replace('-', '')):  # Phone
            continue
        if re.search(r'#\d+|no\.?\s*\d+|ref', text.lower()):  # Reference
            continue
        # Skip TIN, GST, tax registration numbers
        if re.search(r'\b(?:tin|gstin?|pan|vat|ein|ssn|abn|gst\s*no|tax\s*id)\s*:?\s*\d', text.lower()):
            continue
        # Skip invoice/reference numbers
        if re.search(r'\b(?:invoice|inv|order|po|ref|sr|id)\s*(?:no\.?|#|:)\s*\d', text.lower()):
            continue
        # Skip very small amounts (likely quantities, not monetary)
        if amount < 10 and not re.search(r'[\$€£¥₹]', text):
            continue
        # Skip 8+ digit numbers without currency (likely IDs)
        if amount >= 10000000 and not re.search(r'[\$€£¥₹]|rs\.?|inr|usd|kes|ksh|jpy|krw|idr|vnd|ngn|pkr|php|thb|zar|mxn|brl|cop|clp', text.lower()):
            continue
        
        candidate = AmountCandidate(
            value=amount,
            raw_text=text,
            line_idx=token.line_idx,
            x0=token.x0 if hasattr(token, 'x0') else None,
            y0=token.y0 if hasattr(token, 'y0') else None,
        )
        
        # Try to find associated label
        for label_set, amount_type in [
            (TOTAL_LABELS, "total"),
            (SUBTOTAL_LABELS, "subtotal"),
            (TAX_LABELS, "tax"),
            (DISCOUNT_LABELS, "discount"),
        ]:
            label, distance = find_label_for_amount(token, tokens, label_set)
            if label and distance < 200:  # Within reasonable distance
                candidate.label = label
                candidate.label_distance = distance
                candidate.amount_type = amount_type
                candidate.confidence = max(0, 1.0 - distance / 200)
                candidate.reasons.append(f"label_match:{label}")
                break
        
        # Position-based hints
        if hasattr(token, 'line_idx'):
            max_line = max((t.line_idx for t in tokens), default=0)
            # Amounts near bottom are more likely totals
            if token.line_idx > max_line * 0.7:
                if candidate.amount_type == "unknown":
                    candidate.amount_type = "likely_total"
                    candidate.reasons.append("bottom_position")
                    candidate.confidence += 0.2
        
        amount_candidates.append(candidate)
    
    # Step 2: Select best candidates for each type
    totals = [c for c in amount_candidates if c.amount_type == "total"]
    subtotals = [c for c in amount_candidates if c.amount_type == "subtotal"]
    taxes = [c for c in amount_candidates if c.amount_type == "tax"]
    discounts = [c for c in amount_candidates if c.amount_type == "discount"]
    likely_totals = [c for c in amount_candidates if c.amount_type == "likely_total"]
    
    # Prefer "grand total" over simple "total"
    grand_totals = [c for c in totals if c.label and "grand" in c.label.lower()]
    simple_totals = [c for c in totals if c.label and "grand" not in c.label.lower()]
    
    # Sort by confidence
    grand_totals.sort(key=lambda x: -x.confidence)
    simple_totals.sort(key=lambda x: -x.confidence)
    subtotals.sort(key=lambda x: -x.confidence)
    taxes.sort(key=lambda x: -x.confidence)
    
    # Select best total - prefer grand total
    if grand_totals:
        result["total"] = grand_totals[0].value
        result["confidence"] = max(result["confidence"], grand_totals[0].confidence)
        # If we have a simple "total" too, that might be subtotal
        if simple_totals and not subtotals:
            subtotals = simple_totals
    elif simple_totals:
        result["total"] = simple_totals[0].value
        result["confidence"] = max(result["confidence"], simple_totals[0].confidence)
    elif likely_totals:
        # Use largest likely_total as the total
        likely_totals.sort(key=lambda x: -x.value)
        result["total"] = likely_totals[0].value
        result["confidence"] = max(result["confidence"], 0.5)
    
    if subtotals:
        result["subtotal"] = subtotals[0].value
    
    if taxes:
        result["tax"] = taxes[0].value
        # Try to extract tax rate from label or nearby text
        tax_label = taxes[0].label or taxes[0].raw_text or ""
        rate_match = re.search(r'(\d+(?:\.\d+)?)\s*%', tax_label)
        if rate_match:
            result["tax_rate"] = float(rate_match.group(1))
    
    if discounts:
        result["discount"] = discounts[0].value
    
    # Step 3: Validate with mathematical relationships
    validation = {}
    
    if result["total"] and result["subtotal"] and result["tax"]:
        expected_total = result["subtotal"] + result["tax"]
        if result["discount"]:
            expected_total -= result["discount"]
        
        diff = abs(result["total"] - expected_total)
        tolerance = result["total"] * 0.01  # 1% tolerance
        
        if diff <= tolerance:
            validation["math_valid"] = True
            validation["computed_total"] = expected_total
            result["confidence"] = min(1.0, result["confidence"] + 0.3)
        else:
            validation["math_valid"] = False
            validation["computed_total"] = expected_total
            validation["difference"] = diff
            result["confidence"] *= 0.7
    
    elif result["total"] and result["subtotal"]:
        # Infer tax
        inferred_tax = result["total"] - result["subtotal"]
        if inferred_tax > 0 and inferred_tax < result["subtotal"] * 0.5:  # Tax < 50%
            result["tax"] = inferred_tax
            validation["tax_inferred"] = True
            result["confidence"] = max(result["confidence"], 0.6)
    
    elif result["total"] and result["tax"]:
        # Infer subtotal
        inferred_subtotal = result["total"] - result["tax"]
        if inferred_subtotal > 0:
            result["subtotal"] = inferred_subtotal
            validation["subtotal_inferred"] = True
    
    result["validation"] = validation
    result["candidates"] = [
        {
            "value": c.value,
            "label": c.label,
            "type": c.amount_type,
            "confidence": c.confidence,
            "reasons": c.reasons,
        }
        for c in amount_candidates[:15]
    ]
    
    return result


def enhance_amount_extraction(
    tokens: List[Any],
    current_amounts: Dict[str, Any],
    page_width: float = 612,
    page_height: float = 792,
) -> Dict[str, Any]:
    """
    Enhance existing amount extraction with spatial intelligence.
    
    Args:
        tokens: LayoutTokens
        current_amounts: Currently extracted amounts
        page_width: Page width
        page_height: Page height
    
    Returns:
        Dict with enhanced amounts and comparison
    """
    spatial = extract_amounts_with_spatial_intelligence(tokens, page_width, page_height)
    
    result = {
        "spatial_total": spatial.get("total"),
        "spatial_subtotal": spatial.get("subtotal"),
        "spatial_tax": spatial.get("tax"),
        "spatial_tax_rate": spatial.get("tax_rate"),
        "spatial_confidence": spatial.get("confidence", 0.0),
        "current_total": current_amounts.get("total"),
        "current_subtotal": current_amounts.get("subtotal"),
        "current_tax": current_amounts.get("tax"),
        "agreement": {},
        "recommendation": {},
        "validation": spatial.get("validation", {}),
    }
    
    # Check agreement for each field
    for field in ["total", "subtotal", "tax"]:
        spatial_val = spatial.get(field)
        current_val = current_amounts.get(field)
        
        if spatial_val is None and current_val is None:
            result["agreement"][field] = "both_missing"
        elif spatial_val is None:
            result["agreement"][field] = "spatial_missing"
            result["recommendation"][field] = "keep_current"
        elif current_val is None:
            result["agreement"][field] = "current_missing"
            result["recommendation"][field] = "use_spatial"
        elif abs(spatial_val - current_val) < 0.01:
            result["agreement"][field] = "match"
            result["recommendation"][field] = "keep_current"
        else:
            result["agreement"][field] = "mismatch"
            # Prefer spatial if higher confidence and math validates
            if spatial.get("confidence", 0) > 0.7 and spatial.get("validation", {}).get("math_valid"):
                result["recommendation"][field] = "use_spatial"
            else:
                result["recommendation"][field] = "keep_current"
    
    return result


# =============================================================================
# Fraud Detection Signals
# =============================================================================

@dataclass
class FraudSignal:
    """A fraud detection signal with evidence."""
    signal_id: str
    severity: str  # "low", "medium", "high", "critical"
    confidence: float
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""


def detect_amount_anomalies(
    total: Optional[float],
    subtotal: Optional[float],
    tax: Optional[float],
    tax_rate: Optional[float] = None,
    items_sum: Optional[float] = None,
) -> List[FraudSignal]:
    """
    Detect anomalies in amount values.
    
    Checks for:
    1. Math mismatch (subtotal + tax != total)
    2. Unrealistic tax rates
    3. Round number patterns (potential fabrication)
    4. Items sum mismatch
    """
    signals = []
    
    # Math mismatch check
    if total and subtotal and tax:
        expected_total = subtotal + tax
        diff = abs(total - expected_total)
        tolerance = total * 0.01  # 1% tolerance
        
        if diff > tolerance:
            mismatch_pct = (diff / total) * 100
            severity = "high" if mismatch_pct > 5 else "medium"
            signals.append(FraudSignal(
                signal_id="AMOUNT_MATH_MISMATCH",
                severity=severity,
                confidence=min(1.0, mismatch_pct / 10),
                description=f"Subtotal ({subtotal}) + Tax ({tax}) = {expected_total}, but Total is {total}",
                evidence={
                    "expected_total": expected_total,
                    "actual_total": total,
                    "difference": diff,
                    "mismatch_percentage": round(mismatch_pct, 2),
                },
                recommendation="Verify amounts with original receipt",
            ))
    
    # Tax rate check
    if subtotal and tax:
        calculated_rate = (tax / subtotal) * 100
        
        # Common valid tax rates: 0-30%
        if calculated_rate > 30:
            signals.append(FraudSignal(
                signal_id="TAX_RATE_UNREALISTIC",
                severity="high",
                confidence=0.8,
                description=f"Calculated tax rate ({calculated_rate:.1f}%) is unusually high",
                evidence={
                    "calculated_rate": round(calculated_rate, 2),
                    "subtotal": subtotal,
                    "tax": tax,
                    "threshold": 30,
                },
                recommendation="Verify tax rate against local regulations",
            ))
        elif calculated_rate < 0:
            signals.append(FraudSignal(
                signal_id="TAX_RATE_NEGATIVE",
                severity="critical",
                confidence=0.95,
                description="Tax amount is negative, which is invalid",
                evidence={"tax": tax, "subtotal": subtotal},
                recommendation="Flag as potential fraud",
            ))
    
    # Round number pattern (potential fabrication)
    round_count = 0
    for val in [total, subtotal, tax]:
        if val and val > 0:
            # Check if value is suspiciously round (e.g., 1000.00, 500.00)
            if val == int(val) and val >= 100:
                if val % 100 == 0:
                    round_count += 1
    
    if round_count >= 2:
        signals.append(FraudSignal(
            signal_id="ROUND_NUMBER_PATTERN",
            severity="low",
            confidence=0.4,
            description="Multiple amounts are suspiciously round numbers",
            evidence={
                "total": total,
                "subtotal": subtotal,
                "tax": tax,
                "round_count": round_count,
            },
            recommendation="May indicate fabricated amounts",
        ))
    
    # Items sum mismatch
    if items_sum and subtotal:
        diff = abs(items_sum - subtotal)
        if diff > subtotal * 0.01:  # 1% tolerance
            signals.append(FraudSignal(
                signal_id="ITEMS_SUM_MISMATCH",
                severity="medium",
                confidence=0.7,
                description=f"Sum of line items ({items_sum}) doesn't match subtotal ({subtotal})",
                evidence={
                    "items_sum": items_sum,
                    "subtotal": subtotal,
                    "difference": diff,
                },
                recommendation="Verify individual line items",
            ))
    
    return signals


def detect_layout_anomalies(
    tokens: List[Any],
    page_width: float = 612,
    page_height: float = 792,
) -> List[FraudSignal]:
    """
    Detect anomalies in document layout.
    
    Checks for:
    1. Text overlap (potential editing)
    2. Unusual spacing patterns
    3. Poor column alignment
    """
    signals = []
    
    if not tokens:
        return signals
    
    # Get tokens with coordinates
    coord_tokens = [t for t in tokens if hasattr(t, 'has_coords') and t.has_coords]
    
    if len(coord_tokens) < 5:
        return signals  # Not enough data
    
    # Check for text overlap (suspicious - might indicate editing)
    overlaps = []
    for i, t1 in enumerate(coord_tokens):
        for t2 in coord_tokens[i+1:]:
            if t1.page == t2.page:
                # Check if bounding boxes overlap significantly
                x_overlap = max(0, min(t1.x1, t2.x1) - max(t1.x0, t2.x0))
                y_overlap = max(0, min(t1.y1, t2.y1) - max(t1.y0, t2.y0))
                
                if x_overlap > 5 and y_overlap > 5:
                    overlaps.append((t1.text[:20], t2.text[:20]))
    
    if len(overlaps) > 3:
        signals.append(FraudSignal(
            signal_id="TEXT_OVERLAP_DETECTED",
            severity="high",
            confidence=0.75,
            description=f"Multiple text overlaps detected ({len(overlaps)}), may indicate document editing",
            evidence={
                "overlap_count": len(overlaps),
                "examples": overlaps[:3],
            },
            recommendation="Examine original document for tampering",
        ))
    
    # Check for unusual vertical gaps (potential inserted content)
    y_positions = sorted([t.y0 for t in coord_tokens if t.y0 is not None])
    if len(y_positions) > 5:
        gaps = [y_positions[i+1] - y_positions[i] for i in range(len(y_positions)-1)]
        avg_gap = sum(gaps) / len(gaps)
        large_gaps = [g for g in gaps if g > avg_gap * 3]
        
        if len(large_gaps) > 2:
            signals.append(FraudSignal(
                signal_id="UNUSUAL_SPACING",
                severity="low",
                confidence=0.5,
                description="Unusual vertical spacing detected in document",
                evidence={
                    "average_gap": round(avg_gap, 2),
                    "large_gap_count": len(large_gaps),
                    "max_gap": max(gaps),
                },
                recommendation="Check for inserted or deleted content",
            ))
    
    return signals


def detect_content_anomalies(
    tokens: List[Any],
    merchant: Optional[str] = None,
    total: Optional[float] = None,
    receipt_date: Optional[str] = None,
) -> List[FraudSignal]:
    """
    Detect anomalies in document content.
    
    Checks for:
    1. Missing critical fields
    2. Duplicate values
    3. Suspicious merchant names
    4. Future dates
    5. Inconsistent formatting
    6. Suspicious patterns
    """
    signals = []
    
    if not tokens:
        return signals
    
    # Collect all text
    all_text = " ".join(t.text for t in tokens).lower()
    all_text_raw = " ".join(t.text for t in tokens)
    
    # Missing critical fields
    missing_fields = []
    if "total" not in all_text and "amount" not in all_text:
        missing_fields.append("total/amount")
    if "date" not in all_text:
        missing_fields.append("date")
    
    if missing_fields:
        signals.append(FraudSignal(
            signal_id="MISSING_CRITICAL_FIELDS",
            severity="medium",
            confidence=0.6,
            description=f"Document is missing critical fields: {', '.join(missing_fields)}",
            evidence={"missing_fields": missing_fields},
            recommendation="Verify document completeness",
        ))
    
    # Suspicious merchant name patterns
    if merchant:
        merchant_lower = merchant.lower()
        suspicious_patterns = [
            ("test", "Contains 'test'"),
            ("sample", "Contains 'sample'"),
            ("demo", "Contains 'demo'"),
            ("xxx", "Contains placeholder pattern"),
        ]
        
        for pattern, reason in suspicious_patterns:
            if pattern in merchant_lower:
                signals.append(FraudSignal(
                    signal_id="SUSPICIOUS_MERCHANT_NAME",
                    severity="medium",
                    confidence=0.65,
                    description=f"Merchant name '{merchant}' appears suspicious: {reason}",
                    evidence={
                        "merchant": merchant,
                        "pattern_matched": pattern,
                        "reason": reason,
                    },
                    recommendation="Verify merchant legitimacy",
                ))
                break
    
    # Check for duplicate amounts
    amounts = []
    for token in tokens:
        text = token.text.strip()
        amount = extract_amount_from_text(text)
        if amount and amount > 10:
            amounts.append(amount)
    
    if amounts:
        from collections import Counter
        amount_counts = Counter(amounts)
        duplicates = [(amt, count) for amt, count in amount_counts.items() if count > 2]
        
        if duplicates:
            signals.append(FraudSignal(
                signal_id="DUPLICATE_AMOUNTS",
                severity="low",
                confidence=0.45,
                description="Same amount appears multiple times in document",
                evidence={
                    "duplicates": [(amt, count) for amt, count in duplicates[:3]],
                },
                recommendation="Verify each occurrence is intentional",
            ))
    
    # ==========================================================================
    # ADDITIONAL FRAUD SIGNALS
    # ==========================================================================
    
    # 1. Future date detection
    if receipt_date:
        try:
            from datetime import datetime
            # Try common date formats
            date_obj = None
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y"]:
                try:
                    date_obj = datetime.strptime(receipt_date, fmt)
                    break
                except ValueError:
                    continue
            
            if date_obj and date_obj > datetime.now():
                signals.append(FraudSignal(
                    signal_id="FUTURE_DATE",
                    severity="critical",
                    confidence=0.95,
                    description=f"Receipt date ({receipt_date}) is in the future",
                    evidence={"receipt_date": receipt_date, "parsed_date": str(date_obj)},
                    recommendation="Flag as potential fraud - future dates are invalid",
                ))
        except Exception:
            pass
    
    # 2. Inconsistent number formatting (mixing 1,000.00 and 1.000,00)
    comma_decimal_pattern = re.findall(r'\d{1,3}\.\d{3},\d{2}', all_text_raw)  # European: 1.000,00
    period_decimal_pattern = re.findall(r'\d{1,3},\d{3}\.\d{2}', all_text_raw)  # US: 1,000.00
    
    if comma_decimal_pattern and period_decimal_pattern:
        signals.append(FraudSignal(
            signal_id="INCONSISTENT_NUMBER_FORMAT",
            severity="medium",
            confidence=0.7,
            description="Document contains mixed number formats (European and US style)",
            evidence={
                "european_format_count": len(comma_decimal_pattern),
                "us_format_count": len(period_decimal_pattern),
                "examples_european": comma_decimal_pattern[:2],
                "examples_us": period_decimal_pattern[:2],
            },
            recommendation="Verify document origin - legitimate receipts use consistent formatting",
        ))
    
    # 3. Suspiciously low total (potential placeholder)
    if total and total < 1.0 and total > 0:
        signals.append(FraudSignal(
            signal_id="SUSPICIOUSLY_LOW_TOTAL",
            severity="medium",
            confidence=0.6,
            description=f"Total amount ({total}) is suspiciously low",
            evidence={"total": total},
            recommendation="Verify this is not a placeholder or test value",
        ))
    
    # 4. Suspiciously high total (potential typo or manipulation)
    if total and total > 1000000:  # > 1 million
        signals.append(FraudSignal(
            signal_id="UNUSUALLY_HIGH_TOTAL",
            severity="medium",
            confidence=0.5,
            description=f"Total amount ({total:,.2f}) is unusually high",
            evidence={"total": total},
            recommendation="Verify amount is correct and not a data entry error",
        ))
    
    # 5. Lorem ipsum / placeholder text detection
    placeholder_patterns = [
        r"\blorem\s+ipsum\b",
        r"\bplaceholder\b",
        r"\bxxxxx+\b",
        r"\b12345\b.*\b12345\b",  # Repeated placeholder numbers
        r"\btest\s+receipt\b",
        r"\bsample\s+invoice\b",
    ]
    for pattern in placeholder_patterns:
        if re.search(pattern, all_text, re.IGNORECASE):
            signals.append(FraudSignal(
                signal_id="PLACEHOLDER_TEXT_DETECTED",
                severity="high",
                confidence=0.85,
                description="Document contains placeholder or test text",
                evidence={"pattern_matched": pattern},
                recommendation="Flag as likely fake/test document",
            ))
            break
    
    # 6. Inconsistent font sizes (text tokens with very different heights)
    if tokens:
        heights = [t.height for t in tokens if hasattr(t, 'height') and t.height and t.height > 0]
        if len(heights) > 10:
            avg_height = sum(heights) / len(heights)
            outliers = [h for h in heights if h > avg_height * 2.5 or h < avg_height * 0.3]
            outlier_ratio = len(outliers) / len(heights)
            
            if outlier_ratio > 0.15:  # More than 15% are outliers
                signals.append(FraudSignal(
                    signal_id="INCONSISTENT_FONT_SIZES",
                    severity="medium",
                    confidence=0.55,
                    description="Document has inconsistent text sizes (potential editing)",
                    evidence={
                        "average_height": round(avg_height, 2),
                        "outlier_count": len(outliers),
                        "outlier_ratio": round(outlier_ratio, 2),
                    },
                    recommendation="Check for text inserted from different sources",
                ))
    
    # 7. Multiple currency symbols (suspicious for single transaction)
    currency_symbols = re.findall(r'[\$€£¥₹]', all_text_raw)
    unique_currencies = set(currency_symbols)
    if len(unique_currencies) > 1:
        signals.append(FraudSignal(
            signal_id="MULTIPLE_CURRENCIES",
            severity="medium",
            confidence=0.6,
            description="Document contains multiple currency symbols",
            evidence={
                "currencies_found": list(unique_currencies),
                "count": len(currency_symbols),
            },
            recommendation="Verify if multi-currency transaction is legitimate",
        ))
    
    # 8. Sequential/repetitive invoice numbers
    invoice_numbers = re.findall(r'(?:invoice|inv|receipt|rcpt)[\s#:no.-]*(\d{4,})', all_text, re.IGNORECASE)
    if invoice_numbers:
        for num in invoice_numbers:
            # Check for suspicious patterns like 1111, 1234, 0000
            if len(set(num)) == 1:  # All same digit (1111, 2222)
                signals.append(FraudSignal(
                    signal_id="SUSPICIOUS_INVOICE_NUMBER",
                    severity="medium",
                    confidence=0.6,
                    description=f"Invoice number '{num}' has suspicious pattern (all same digits)",
                    evidence={"invoice_number": num},
                    recommendation="Verify invoice number authenticity",
                ))
                break
            if num in ["1234", "12345", "123456", "1234567", "12345678"]:
                signals.append(FraudSignal(
                    signal_id="SUSPICIOUS_INVOICE_NUMBER",
                    severity="high",
                    confidence=0.75,
                    description=f"Invoice number '{num}' is a common placeholder sequence",
                    evidence={"invoice_number": num},
                    recommendation="Flag as likely fake - sequential placeholder",
                ))
                break
    
    # ==========================================================================
    # 9. GST/TIN/Tax ID Validation
    # ==========================================================================
    gstin_pattern = re.findall(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b', all_text_raw.upper())
    for gstin in gstin_pattern:
        if not _validate_gstin_checksum(gstin):
            signals.append(FraudSignal(
                signal_id="INVALID_GSTIN_CHECKSUM",
                severity="critical",
                confidence=0.95,
                description=f"GSTIN '{gstin}' has invalid checksum - likely fabricated",
                evidence={"gstin": gstin},
                recommendation="GSTIN checksum validation failed - verify with GST portal",
            ))
    
    # ==========================================================================
    # 10. Impossible Date Detection
    # ==========================================================================
    date_patterns = re.findall(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', all_text_raw)
    for match in date_patterns:
        day, month, year = match
        try:
            d, m = int(day), int(month)
            # Check for impossible dates
            if m > 12 or m < 1:
                signals.append(FraudSignal(
                    signal_id="IMPOSSIBLE_DATE",
                    severity="high",
                    confidence=0.9,
                    description=f"Invalid month in date: {day}/{month}/{year}",
                    evidence={"date": f"{day}/{month}/{year}", "issue": "invalid_month"},
                    recommendation="Date contains impossible month value",
                ))
            elif d > 31 or d < 1:
                signals.append(FraudSignal(
                    signal_id="IMPOSSIBLE_DATE",
                    severity="high",
                    confidence=0.9,
                    description=f"Invalid day in date: {day}/{month}/{year}",
                    evidence={"date": f"{day}/{month}/{year}", "issue": "invalid_day"},
                    recommendation="Date contains impossible day value",
                ))
            elif m in [4, 6, 9, 11] and d > 30:
                signals.append(FraudSignal(
                    signal_id="IMPOSSIBLE_DATE",
                    severity="high",
                    confidence=0.9,
                    description=f"Invalid date: {day}/{month}/{year} - month has only 30 days",
                    evidence={"date": f"{day}/{month}/{year}", "issue": "day_exceeds_month"},
                    recommendation="Date is impossible for this month",
                ))
            elif m == 2 and d > 29:
                signals.append(FraudSignal(
                    signal_id="IMPOSSIBLE_DATE",
                    severity="high",
                    confidence=0.9,
                    description=f"Invalid date: {day}/{month}/{year} - February never has {d} days",
                    evidence={"date": f"{day}/{month}/{year}", "issue": "feb_invalid"},
                    recommendation="February date is impossible",
                ))
        except ValueError:
            pass
    
    # ==========================================================================
    # 11. Suspicious Time Detection (purchases at unusual hours)
    # ==========================================================================
    time_patterns = re.findall(r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?\b', all_text_raw)
    for match in time_patterns:
        hour, minute = int(match[0]), int(match[1])
        am_pm = match[3].upper() if match[3] else None
        
        # Convert to 24-hour
        if am_pm == 'PM' and hour != 12:
            hour += 12
        elif am_pm == 'AM' and hour == 12:
            hour = 0
        
        # Flag unusual hours (midnight to 5am)
        if 0 <= hour < 5:
            signals.append(FraudSignal(
                signal_id="UNUSUAL_TRANSACTION_TIME",
                severity="low",
                confidence=0.4,
                description=f"Transaction at unusual hour: {match[0]}:{match[1]} {am_pm or ''}",
                evidence={"time": f"{match[0]}:{match[1]}", "hour_24": hour},
                recommendation="Verify if business operates at this hour",
            ))
    
    # ==========================================================================
    # 12. Phone Number Format Validation
    # ==========================================================================
    phone_patterns = re.findall(r'(?:phone|tel|mobile|contact)[\s:]*([+\d\s\-().]{8,20})', all_text, re.IGNORECASE)
    for phone in phone_patterns:
        digits_only = re.sub(r'\D', '', phone)
        # Check for suspicious patterns
        if len(set(digits_only)) <= 2:  # All same or two digits
            signals.append(FraudSignal(
                signal_id="SUSPICIOUS_PHONE_NUMBER",
                severity="medium",
                confidence=0.7,
                description=f"Phone number appears fake: '{phone}' (repetitive digits)",
                evidence={"phone": phone},
                recommendation="Verify phone number authenticity",
            ))
        elif digits_only in ["1234567890", "0987654321", "1111111111", "0000000000"]:
            signals.append(FraudSignal(
                signal_id="PLACEHOLDER_PHONE_NUMBER",
                severity="high",
                confidence=0.85,
                description=f"Phone number is a common placeholder: '{phone}'",
                evidence={"phone": phone},
                recommendation="Fake phone number detected",
            ))
    
    # ==========================================================================
    # 13. Email Domain Validation
    # ==========================================================================
    email_patterns = re.findall(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', all_text_raw)
    suspicious_domains = ['example.com', 'test.com', 'fake.com', 'temp.com', 'dummy.com', 'sample.com']
    for email in email_patterns:
        domain = email.split('@')[1].lower()
        if domain in suspicious_domains:
            signals.append(FraudSignal(
                signal_id="SUSPICIOUS_EMAIL_DOMAIN",
                severity="high",
                confidence=0.85,
                description=f"Email uses placeholder domain: '{email}'",
                evidence={"email": email, "domain": domain},
                recommendation="Email domain is a known placeholder",
            ))
        # Check for all-numeric local part (often fake)
        local_part = email.split('@')[0]
        if local_part.isdigit():
            signals.append(FraudSignal(
                signal_id="SUSPICIOUS_EMAIL_FORMAT",
                severity="medium",
                confidence=0.6,
                description=f"Email has suspicious format (all numeric): '{email}'",
                evidence={"email": email},
                recommendation="Unusual email format detected",
            ))
    
    # ==========================================================================
    # 14. Duplicate Exact Amounts (potential copy-paste)
    # ==========================================================================
    amount_tokens = re.findall(r'[\$₹€£]\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b', all_text_raw)
    if len(amount_tokens) > 3:
        amount_counts = {}
        for amt in amount_tokens:
            amount_counts[amt] = amount_counts.get(amt, 0) + 1
        
        # Check for exact same amount appearing 3+ times (excluding common ones like 0.00)
        for amt, count in amount_counts.items():
            if count >= 3 and amt not in ['0.00', '0', '1.00', '1']:
                signals.append(FraudSignal(
                    signal_id="REPEATED_EXACT_AMOUNT",
                    severity="medium",
                    confidence=0.6,
                    description=f"Same exact amount '{amt}' appears {count} times - possible copy-paste",
                    evidence={"amount": amt, "occurrences": count},
                    recommendation="Check if duplicate amounts are intentional",
                ))
    
    return signals


def _validate_gstin_checksum(gstin: str) -> bool:
    """
    Validate Indian GSTIN checksum (15 characters).
    
    Format: 22AAAAA0000A1Z5
    - First 2: State code (01-37)
    - Next 10: PAN
    - 13th: Entity number (1-9, A-Z)
    - 14th: Z (default)
    - 15th: Check digit
    """
    if len(gstin) != 15:
        return False
    
    # Check state code (01-37)
    try:
        state_code = int(gstin[:2])
        if state_code < 1 or state_code > 37:
            return False
    except ValueError:
        return False
    
    # Checksum calculation
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    factor = 1
    total = 0
    
    for i in range(14):
        char = gstin[i]
        digit = chars.index(char)
        digit = digit * factor
        digit = (digit // 36) + (digit % 36)
        total += digit
        factor = 2 if factor == 1 else 1
    
    remainder = total % 36
    check_char = chars[(36 - remainder) % 36]
    
    return gstin[14] == check_char


# =============================================================================
# Font Inconsistency Detection
# =============================================================================

@dataclass
class FontMetrics:
    """Metrics for a group of tokens to analyze font consistency."""
    heights: List[float] = field(default_factory=list)
    baselines: List[float] = field(default_factory=list)  # y1 values (bottom of text)
    aspect_ratios: List[float] = field(default_factory=list)  # width/height
    char_densities: List[float] = field(default_factory=list)  # chars per unit width
    confidences: List[float] = field(default_factory=list)
    inter_word_gaps: List[float] = field(default_factory=list)


def detect_font_inconsistencies(tokens: List[Any]) -> List[FraudSignal]:
    """
    Detect font inconsistencies using token geometry analysis.
    
    This replicates how a human (or AI) detects font manipulation:
    1. Baseline misalignment - text on same line should align at bottom
    2. Height variation within lines - same line text should have similar heights
    3. Character density anomalies - chars per unit width should be consistent
    4. OCR confidence clustering - edited text often has different confidence
    5. Aspect ratio anomalies - width/height ratio for similar tokens
    6. Inter-word spacing anomalies - unusual gaps between words
    7. Vertical position jumps - spliced text may have y-position discontinuities
    
    Args:
        tokens: List of tokens with bounding box coordinates
        
    Returns:
        List of FraudSignal objects for detected font anomalies
    """
    signals = []
    
    if not tokens or len(tokens) < 5:
        return signals
    
    # Filter tokens with valid coordinates
    valid_tokens = [
        t for t in tokens 
        if hasattr(t, 'x0') and hasattr(t, 'y0') and hasattr(t, 'x1') and hasattr(t, 'y1')
        and t.x0 is not None and t.y0 is not None and t.x1 is not None and t.y1 is not None
        and hasattr(t, 'text') and t.text and len(t.text.strip()) > 0
    ]
    
    if len(valid_tokens) < 5:
        return signals
    
    # ==========================================================================
    # 1. Group tokens by line (using y-position clustering)
    # ==========================================================================
    lines = _group_tokens_into_lines(valid_tokens)
    
    # ==========================================================================
    # 2. Analyze baseline alignment within each line
    # ==========================================================================
    baseline_anomalies = _detect_baseline_misalignment(lines)
    if baseline_anomalies:
        signals.append(FraudSignal(
            signal_id="BASELINE_MISALIGNMENT",
            severity="high",
            confidence=min(0.85, 0.5 + len(baseline_anomalies) * 0.1),
            description=f"Text baseline misalignment detected on {len(baseline_anomalies)} line(s) - indicates spliced or edited text",
            evidence={
                "affected_lines": len(baseline_anomalies),
                "examples": baseline_anomalies[:3],
            },
            recommendation="Inspect flagged lines for text that appears vertically shifted compared to surrounding text",
        ))
    
    # ==========================================================================
    # 3. Analyze height variation within lines
    # ==========================================================================
    height_anomalies = _detect_height_variation_in_lines(lines)
    if height_anomalies:
        signals.append(FraudSignal(
            signal_id="INTRA_LINE_HEIGHT_VARIATION",
            severity="high",
            confidence=min(0.85, 0.55 + len(height_anomalies) * 0.1),
            description=f"Abnormal text height variation within {len(height_anomalies)} line(s) - different fonts mixed",
            evidence={
                "affected_lines": len(height_anomalies),
                "examples": height_anomalies[:3],
            },
            recommendation="Check for text inserted from different source with different font size",
        ))
    
    # ==========================================================================
    # 4. Analyze character density (chars per unit width)
    # ==========================================================================
    density_anomalies = _detect_char_density_anomalies(valid_tokens)
    if density_anomalies:
        signals.append(FraudSignal(
            signal_id="CHARACTER_DENSITY_ANOMALY",
            severity="medium",
            confidence=0.65,
            description="Inconsistent character density detected - may indicate different fonts or manual spacing",
            evidence={
                "anomaly_count": len(density_anomalies),
                "examples": density_anomalies[:3],
            },
            recommendation="Review tokens with unusual character spacing/density",
        ))
    
    # ==========================================================================
    # 5. Analyze OCR confidence patterns
    # ==========================================================================
    confidence_anomalies = _detect_confidence_clustering(valid_tokens)
    if confidence_anomalies:
        signals.append(FraudSignal(
            signal_id="OCR_CONFIDENCE_ANOMALY",
            severity="medium",
            confidence=0.6,
            description="OCR confidence drops on specific tokens - may indicate edited/synthetic text",
            evidence={
                "low_confidence_tokens": len(confidence_anomalies),
                "examples": confidence_anomalies[:5],
            },
            recommendation="Edited text often renders differently, causing OCR confidence drops",
        ))
    
    # ==========================================================================
    # 6. Analyze inter-word spacing within lines
    # ==========================================================================
    spacing_anomalies = _detect_spacing_anomalies(lines)
    if spacing_anomalies:
        severity = "high" if len(spacing_anomalies) > 2 else "medium"
        signals.append(FraudSignal(
            signal_id="INTER_WORD_SPACING_ANOMALY",
            severity=severity,
            confidence=min(0.8, 0.5 + len(spacing_anomalies) * 0.1),
            description=f"Abnormal spacing between words on {len(spacing_anomalies)} line(s) - text may be manually placed",
            evidence={
                "affected_lines": len(spacing_anomalies),
                "examples": spacing_anomalies[:3],
            },
            recommendation="Check for text that appears manually positioned rather than naturally printed",
        ))
    
    # ==========================================================================
    # 7. Detect aspect ratio anomalies (width/height ratio)
    # ==========================================================================
    aspect_anomalies = _detect_aspect_ratio_anomalies(valid_tokens)
    if aspect_anomalies:
        signals.append(FraudSignal(
            signal_id="ASPECT_RATIO_ANOMALY",
            severity="medium",
            confidence=0.55,
            description="Text aspect ratio anomalies detected - possible font stretching or different font family",
            evidence={
                "anomaly_count": len(aspect_anomalies),
                "examples": aspect_anomalies[:3],
            },
            recommendation="Check for text that appears stretched or compressed compared to surrounding text",
        ))
    
    # ==========================================================================
    # 8. Detect vertical position discontinuities
    # ==========================================================================
    vertical_jumps = _detect_vertical_discontinuities(lines)
    if vertical_jumps:
        signals.append(FraudSignal(
            signal_id="VERTICAL_POSITION_DISCONTINUITY",
            severity="medium",
            confidence=0.5,
            description="Irregular vertical spacing between lines - possible spliced content",
            evidence={
                "jump_count": len(vertical_jumps),
                "examples": vertical_jumps[:3],
            },
            recommendation="Check for sections that may have been inserted between existing content",
        ))
    
    return signals


def _group_tokens_into_lines(tokens: List[Any], tolerance: float = 5.0) -> Dict[int, List[Any]]:
    """
    Group tokens into lines based on vertical position clustering.
    
    Tokens are on the same line if their vertical centers are within tolerance.
    """
    if not tokens:
        return {}
    
    # Sort by vertical position
    sorted_tokens = sorted(tokens, key=lambda t: (t.y0 + t.y1) / 2)
    
    lines = {}
    current_line = [sorted_tokens[0]]
    line_idx = 0
    current_y = (sorted_tokens[0].y0 + sorted_tokens[0].y1) / 2
    
    for token in sorted_tokens[1:]:
        token_y = (token.y0 + token.y1) / 2
        
        # Check if token is on the same line (within tolerance)
        if abs(token_y - current_y) <= tolerance:
            current_line.append(token)
        else:
            # Save current line and start new one
            if len(current_line) >= 2:  # Only keep lines with 2+ tokens
                lines[line_idx] = sorted(current_line, key=lambda t: t.x0)  # Sort by x position
                line_idx += 1
            current_line = [token]
            current_y = token_y
    
    # Don't forget the last line
    if len(current_line) >= 2:
        lines[line_idx] = sorted(current_line, key=lambda t: t.x0)
    
    return lines


def _detect_baseline_misalignment(lines: Dict[int, List[Any]], threshold: float = 3.0) -> List[Dict]:
    """
    Detect lines where tokens have misaligned baselines.
    
    Baseline is the bottom of the text (y1). On a properly printed line,
    all text should share approximately the same baseline.
    """
    anomalies = []
    
    for line_idx, tokens in lines.items():
        if len(tokens) < 3:
            continue
        
        baselines = [t.y1 for t in tokens]
        avg_baseline = sum(baselines) / len(baselines)
        
        # Find tokens that deviate significantly from average baseline
        deviations = []
        for i, token in enumerate(tokens):
            deviation = abs(token.y1 - avg_baseline)
            if deviation > threshold:
                deviations.append({
                    "text": token.text[:20],
                    "deviation": round(deviation, 2),
                    "expected_baseline": round(avg_baseline, 2),
                    "actual_baseline": round(token.y1, 2),
                })
        
        # If more than 20% of tokens have baseline issues, flag the line
        if len(deviations) >= 1 and len(deviations) / len(tokens) >= 0.15:
            anomalies.append({
                "line_idx": line_idx,
                "token_count": len(tokens),
                "misaligned_count": len(deviations),
                "examples": deviations[:2],
            })
    
    return anomalies


def _detect_height_variation_in_lines(lines: Dict[int, List[Any]], cv_threshold: float = 0.25) -> List[Dict]:
    """
    Detect lines with abnormal height variation.
    
    Uses coefficient of variation (CV = stddev/mean). Normal printed text
    should have CV < 0.15. Higher values indicate mixed fonts.
    """
    anomalies = []
    
    for line_idx, tokens in lines.items():
        if len(tokens) < 3:
            continue
        
        heights = [abs(t.y1 - t.y0) for t in tokens if abs(t.y1 - t.y0) > 0]
        if len(heights) < 3:
            continue
        
        avg_height = sum(heights) / len(heights)
        if avg_height == 0:
            continue
        
        # Calculate standard deviation
        variance = sum((h - avg_height) ** 2 for h in heights) / len(heights)
        std_dev = variance ** 0.5
        cv = std_dev / avg_height
        
        if cv > cv_threshold:
            # Find the outlier tokens
            outliers = []
            for token in tokens:
                h = abs(token.y1 - token.y0)
                if h > 0 and abs(h - avg_height) > std_dev * 1.5:
                    outliers.append({
                        "text": token.text[:20],
                        "height": round(h, 2),
                        "avg_height": round(avg_height, 2),
                    })
            
            anomalies.append({
                "line_idx": line_idx,
                "cv": round(cv, 3),
                "avg_height": round(avg_height, 2),
                "outliers": outliers[:2],
            })
    
    return anomalies


def _detect_char_density_anomalies(tokens: List[Any], z_threshold: float = 2.5) -> List[Dict]:
    """
    Detect tokens with abnormal character density (chars per unit width).
    
    Same font should have consistent character density. Anomalies may indicate
    different fonts or manually adjusted spacing.
    """
    anomalies = []
    
    # Calculate char density for each token
    densities = []
    for token in tokens:
        width = abs(token.x1 - token.x0)
        if width > 0 and len(token.text.strip()) >= 2:
            density = len(token.text.strip()) / width
            densities.append((token, density))
    
    if len(densities) < 10:
        return anomalies
    
    # Calculate mean and std dev
    density_values = [d[1] for d in densities]
    avg_density = sum(density_values) / len(density_values)
    variance = sum((d - avg_density) ** 2 for d in density_values) / len(density_values)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return anomalies
    
    # Find outliers using z-score
    for token, density in densities:
        z_score = abs(density - avg_density) / std_dev
        if z_score > z_threshold:
            anomalies.append({
                "text": token.text[:20],
                "density": round(density, 4),
                "avg_density": round(avg_density, 4),
                "z_score": round(z_score, 2),
            })
    
    return anomalies


def _detect_confidence_clustering(tokens: List[Any], threshold: float = 0.7) -> List[Dict]:
    """
    Detect tokens with significantly lower OCR confidence.
    
    Edited or synthetic text often has different rendering characteristics,
    causing OCR engines to have lower confidence on those regions.
    """
    anomalies = []
    
    # Get tokens with confidence scores
    tokens_with_conf = [
        t for t in tokens 
        if hasattr(t, 'confidence') and t.confidence is not None
    ]
    
    if len(tokens_with_conf) < 5:
        return anomalies
    
    # Calculate average confidence
    confidences = [t.confidence for t in tokens_with_conf]
    avg_conf = sum(confidences) / len(confidences)
    
    # Find tokens with significantly lower confidence
    for token in tokens_with_conf:
        # Token confidence is much lower than average
        if token.confidence < threshold and token.confidence < avg_conf * 0.8:
            # Skip very short tokens (often noise)
            if len(token.text.strip()) < 2:
                continue
            anomalies.append({
                "text": token.text[:20],
                "confidence": round(token.confidence, 3),
                "avg_confidence": round(avg_conf, 3),
            })
    
    return anomalies


def _detect_spacing_anomalies(lines: Dict[int, List[Any]], z_threshold: float = 2.5) -> List[Dict]:
    """
    Detect lines with abnormal inter-word spacing.
    
    Normal printed text has consistent spacing. Excessive or inconsistent
    gaps often indicate manual text placement or editing.
    """
    anomalies = []
    
    # Collect all inter-word gaps across lines
    all_gaps = []
    line_gaps = {}
    
    for line_idx, tokens in lines.items():
        if len(tokens) < 3:
            continue
        
        gaps = []
        for i in range(len(tokens) - 1):
            gap = tokens[i + 1].x0 - tokens[i].x1
            if gap > 0:  # Only positive gaps (tokens not overlapping)
                gaps.append(gap)
                all_gaps.append(gap)
        
        if gaps:
            line_gaps[line_idx] = gaps
    
    if len(all_gaps) < 10:
        return anomalies
    
    # Calculate global statistics
    avg_gap = sum(all_gaps) / len(all_gaps)
    variance = sum((g - avg_gap) ** 2 for g in all_gaps) / len(all_gaps)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return anomalies
    
    # Check each line for abnormal spacing
    for line_idx, gaps in line_gaps.items():
        # Calculate line's average gap
        line_avg = sum(gaps) / len(gaps)
        
        # Check for excessive gaps (potential manual spacing)
        excessive_gaps = [g for g in gaps if g > avg_gap + z_threshold * std_dev]
        
        # Check for high variance within line
        line_variance = sum((g - line_avg) ** 2 for g in gaps) / len(gaps) if gaps else 0
        line_std = line_variance ** 0.5
        line_cv = line_std / line_avg if line_avg > 0 else 0
        
        if excessive_gaps or line_cv > 0.5:
            anomalies.append({
                "line_idx": line_idx,
                "excessive_gaps": len(excessive_gaps),
                "max_gap": round(max(gaps), 2) if gaps else 0,
                "avg_gap": round(line_avg, 2),
                "cv": round(line_cv, 3),
            })
    
    return anomalies


def _detect_aspect_ratio_anomalies(tokens: List[Any], z_threshold: float = 2.5) -> List[Dict]:
    """
    Detect tokens with abnormal aspect ratios (width/height).
    
    Stretched or compressed text has different aspect ratios than normal text.
    """
    anomalies = []
    
    # Calculate aspect ratio for each token (only tokens with reasonable size)
    ratios = []
    for token in tokens:
        width = abs(token.x1 - token.x0)
        height = abs(token.y1 - token.y0)
        
        if height > 2 and width > 2 and len(token.text.strip()) >= 2:
            # Normalize by character count for fair comparison
            ratio = (width / len(token.text.strip())) / height
            ratios.append((token, ratio))
    
    if len(ratios) < 10:
        return anomalies
    
    # Calculate statistics
    ratio_values = [r[1] for r in ratios]
    avg_ratio = sum(ratio_values) / len(ratio_values)
    variance = sum((r - avg_ratio) ** 2 for r in ratio_values) / len(ratio_values)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return anomalies
    
    # Find outliers
    for token, ratio in ratios:
        z_score = abs(ratio - avg_ratio) / std_dev
        if z_score > z_threshold:
            anomalies.append({
                "text": token.text[:20],
                "aspect_ratio": round(ratio, 3),
                "avg_ratio": round(avg_ratio, 3),
                "z_score": round(z_score, 2),
            })
    
    return anomalies


def _detect_vertical_discontinuities(lines: Dict[int, List[Any]], z_threshold: float = 2.5) -> List[Dict]:
    """
    Detect irregular vertical spacing between lines.
    
    Spliced content often has different line spacing than the rest of the document.
    """
    anomalies = []
    
    if len(lines) < 4:
        return anomalies
    
    # Calculate line positions (average y of each line)
    line_positions = []
    for line_idx in sorted(lines.keys()):
        tokens = lines[line_idx]
        avg_y = sum((t.y0 + t.y1) / 2 for t in tokens) / len(tokens)
        line_positions.append((line_idx, avg_y))
    
    # Calculate line spacings
    spacings = []
    for i in range(len(line_positions) - 1):
        spacing = line_positions[i + 1][1] - line_positions[i][1]
        if spacing > 0:
            spacings.append((line_positions[i][0], line_positions[i + 1][0], spacing))
    
    if len(spacings) < 3:
        return anomalies
    
    # Calculate statistics
    spacing_values = [s[2] for s in spacings]
    avg_spacing = sum(spacing_values) / len(spacing_values)
    variance = sum((s - avg_spacing) ** 2 for s in spacing_values) / len(spacing_values)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return anomalies
    
    # Find outliers
    for line1, line2, spacing in spacings:
        z_score = abs(spacing - avg_spacing) / std_dev
        if z_score > z_threshold:
            anomalies.append({
                "between_lines": f"{line1}-{line2}",
                "spacing": round(spacing, 2),
                "avg_spacing": round(avg_spacing, 2),
                "z_score": round(z_score, 2),
            })
    
    return anomalies


# =============================================================================
# Address Fraud Detection
# =============================================================================

# Country-specific ZIP/postal code patterns
ZIP_PATTERNS = {
    "US": r"\b\d{5}(-\d{4})?\b",  # 12345 or 12345-6789
    "IN": r"\b\d{6}\b",  # 110001
    "UK": r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",  # SW1A 1AA
    "CA": r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b",  # K1A 0B1
    "AU": r"\b\d{4}\b",  # 2000
    "DE": r"\b\d{5}\b",  # 10115
}

# US State abbreviations to full names
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

# Indian states
INDIAN_STATES = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar",
    "CG": "Chhattisgarh", "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh",
    "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra",
    "MN": "Manipur", "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha",
    "PB": "Punjab", "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TS": "Telangana",
    "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal",
    "DL": "Delhi", "JK": "Jammu and Kashmir", "LA": "Ladakh",
}

# US ZIP code to state prefix mapping (first 3 digits)
US_ZIP_STATE_PREFIX = {
    # Northeast
    "006": "PR", "007": "PR", "008": "PR", "009": "PR",  # Puerto Rico
    "010": "MA", "011": "MA", "012": "MA", "013": "MA", "014": "MA",
    "015": "MA", "016": "MA", "017": "MA", "018": "MA", "019": "MA",
    "020": "MA", "021": "MA", "022": "MA", "023": "MA", "024": "MA",
    "025": "MA", "026": "MA", "027": "MA",
    "028": "RI", "029": "RI",
    "030": "NH", "031": "NH", "032": "NH", "033": "NH", "034": "NH",
    "035": "VT", "036": "VT", "037": "VT", "038": "VT", "039": "ME",
    "040": "ME", "041": "ME", "042": "ME", "043": "ME", "044": "ME",
    "045": "ME", "046": "ME", "047": "ME", "048": "ME", "049": "ME",
    # New York
    "100": "NY", "101": "NY", "102": "NY", "103": "NY", "104": "NY",
    "105": "NY", "106": "NY", "107": "NY", "108": "NY", "109": "NY",
    "110": "NY", "111": "NY", "112": "NY", "113": "NY", "114": "NY",
    "115": "NY", "116": "NY", "117": "NY", "118": "NY", "119": "NY",
    "120": "NY", "121": "NY", "122": "NY", "123": "NY", "124": "NY",
    "125": "NY", "126": "NY", "127": "NY", "128": "NY", "129": "NY",
    "130": "NY", "131": "NY", "132": "NY", "133": "NY", "134": "NY",
    "135": "NY", "136": "NY", "137": "NY", "138": "NY", "139": "NY",
    "140": "NY", "141": "NY", "142": "NY", "143": "NY", "144": "NY",
    "145": "NY", "146": "NY", "147": "NY", "148": "NY", "149": "NY",
    # New Jersey
    "070": "NJ", "071": "NJ", "072": "NJ", "073": "NJ", "074": "NJ",
    "075": "NJ", "076": "NJ", "077": "NJ", "078": "NJ", "079": "NJ",
    "080": "NJ", "081": "NJ", "082": "NJ", "083": "NJ", "084": "NJ",
    "085": "NJ", "086": "NJ", "087": "NJ", "088": "NJ", "089": "NJ",
    # Pennsylvania
    "150": "PA", "151": "PA", "152": "PA", "153": "PA", "154": "PA",
    "155": "PA", "156": "PA", "157": "PA", "158": "PA", "159": "PA",
    "160": "PA", "161": "PA", "162": "PA", "163": "PA", "164": "PA",
    "165": "PA", "166": "PA", "167": "PA", "168": "PA", "169": "PA",
    "170": "PA", "171": "PA", "172": "PA", "173": "PA", "174": "PA",
    "175": "PA", "176": "PA", "177": "PA", "178": "PA", "179": "PA",
    "180": "PA", "181": "PA", "182": "PA", "183": "PA", "184": "PA",
    "185": "PA", "186": "PA", "187": "PA", "188": "PA", "189": "PA",
    "190": "PA", "191": "PA",
    # Texas
    "750": "TX", "751": "TX", "752": "TX", "753": "TX", "754": "TX",
    "755": "TX", "756": "TX", "757": "TX", "758": "TX", "759": "TX",
    "760": "TX", "761": "TX", "762": "TX", "763": "TX", "764": "TX",
    "765": "TX", "766": "TX", "767": "TX", "768": "TX", "769": "TX",
    "770": "TX", "771": "TX", "772": "TX", "773": "TX", "774": "TX",
    "775": "TX", "776": "TX", "777": "TX", "778": "TX", "779": "TX",
    "780": "TX", "781": "TX", "782": "TX", "783": "TX", "784": "TX",
    "785": "TX", "786": "TX", "787": "TX", "788": "TX", "789": "TX",
    "790": "TX", "791": "TX", "792": "TX", "793": "TX", "794": "TX",
    "795": "TX", "796": "TX", "797": "TX", "798": "TX", "799": "TX",
    # California
    "900": "CA", "901": "CA", "902": "CA", "903": "CA", "904": "CA",
    "905": "CA", "906": "CA", "907": "CA", "908": "CA", "909": "CA",
    "910": "CA", "911": "CA", "912": "CA", "913": "CA", "914": "CA",
    "915": "CA", "916": "CA", "917": "CA", "918": "CA", "919": "CA",
    "920": "CA", "921": "CA", "922": "CA", "923": "CA", "924": "CA",
    "925": "CA", "926": "CA", "927": "CA", "928": "CA",
    # Florida
    "320": "FL", "321": "FL", "322": "FL", "323": "FL", "324": "FL",
    "325": "FL", "326": "FL", "327": "FL", "328": "FL", "329": "FL",
    "330": "FL", "331": "FL", "332": "FL", "333": "FL", "334": "FL",
    "335": "FL", "336": "FL", "337": "FL", "338": "FL", "339": "FL",
    "340": "FL", "341": "FL", "342": "FL", "344": "FL", "346": "FL",
    # Add more as needed...
}

# Known fake/test addresses
FAKE_ADDRESS_PATTERNS = [
    r"123\s+main\s+st",
    r"123\s+test\s+",
    r"fake\s+street",
    r"nowhere\s+lane",
    r"example\s+(street|road|ave)",
    r"lorem\s+ipsum",
    r"1234\s+street",
    r"abc\s+road",
    r"xyz\s+avenue",
]

# Indian PIN code to state mapping (first 2 digits)
INDIAN_PIN_STATE = {
    "11": "DL", "12": "HR", "13": "HR", "14": "PB", "15": "PB", "16": "PB",
    "17": "HP", "18": "JK", "19": "JK",
    "20": "UP", "21": "UP", "22": "UP", "23": "UP", "24": "UP", "25": "UP",
    "26": "UP", "27": "UP", "28": "UP",
    "30": "RJ", "31": "RJ", "32": "RJ", "33": "RJ", "34": "RJ",
    "36": "GJ", "37": "GJ", "38": "GJ", "39": "GJ",
    "40": "MH", "41": "MH", "42": "MH", "43": "MH", "44": "MH", "45": "MH",
    "50": "TS", "51": "TS", "52": "AP", "53": "AP",
    "56": "KA", "57": "KA", "58": "KA", "59": "KA",
    "60": "TN", "61": "TN", "62": "TN", "63": "TN", "64": "TN",
    "67": "KL", "68": "KL", "69": "KL",
    "70": "WB", "71": "WB", "72": "WB", "73": "WB", "74": "WB",
    "75": "OD", "76": "OD", "77": "OD",
    "78": "AS", "79": "AR",
    "80": "BR", "81": "BR", "82": "BR", "83": "JH", "84": "JH", "85": "JH",
    "45": "MP", "46": "MP", "47": "MP", "48": "MP", "49": "CG",
}


@dataclass
class ExtractedAddress:
    """Extracted address components."""
    full_text: str
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    line_idx: int = 0
    confidence: float = 0.0
    issues: List[str] = field(default_factory=list)


def extract_addresses_from_tokens(tokens: List[Any]) -> List[ExtractedAddress]:
    """
    Extract address components from document tokens.
    
    Looks for patterns like:
    - Street address lines
    - City, State ZIP patterns
    - Country names
    """
    addresses = []
    
    # Combine consecutive lines that might form an address
    lines_text = {}
    for token in tokens:
        line_idx = token.line_idx
        if line_idx not in lines_text:
            lines_text[line_idx] = []
        lines_text[line_idx].append(token.text.strip())
    
    # Join tokens per line
    lines = {idx: " ".join(texts) for idx, texts in lines_text.items()}
    sorted_lines = sorted(lines.items())
    
    # Look for address patterns
    for i, (line_idx, line_text) in enumerate(sorted_lines):
        address = None
        
        # US address: City, ST ZIP
        us_match = re.search(
            r'([A-Za-z\s]+),\s*([A-Z]{2})[\s,-]+(\d{5}(?:-\d{4})?)',
            line_text
        )
        if us_match:
            city, state, zip_code = us_match.groups()
            address = ExtractedAddress(
                full_text=line_text,
                city=city.strip(),
                state_code=state,
                state=US_STATES.get(state, state),
                zip_code=zip_code,
                country="United States",
                country_code="US",
                line_idx=line_idx,
                confidence=0.8,
            )
        
        # Indian address: City, State - PIN or City, PIN
        if not address:
            india_match = re.search(
                r'([A-Za-z\s]+),\s*(?:([A-Za-z\s]+),?\s*)?(\d{6})',
                line_text
            )
            if india_match:
                city = india_match.group(1).strip()
                state = india_match.group(2).strip() if india_match.group(2) else None
                pin = india_match.group(3)
                
                # Detect state from PIN prefix
                pin_prefix = pin[:2]
                detected_state_code = INDIAN_PIN_STATE.get(pin_prefix)
                
                address = ExtractedAddress(
                    full_text=line_text,
                    city=city,
                    state=state,
                    state_code=detected_state_code,
                    zip_code=pin,
                    country="India",
                    country_code="IN",
                    line_idx=line_idx,
                    confidence=0.7,
                )
        
        # UK address: Postcode pattern
        if not address:
            uk_match = re.search(
                r'([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})',
                line_text, re.IGNORECASE
            )
            if uk_match:
                postcode = uk_match.group(1).upper()
                address = ExtractedAddress(
                    full_text=line_text,
                    zip_code=postcode,
                    country="United Kingdom",
                    country_code="UK",
                    line_idx=line_idx,
                    confidence=0.6,
                )
        
        # Street address detection (to associate with city/state found nearby)
        if not address:
            street_match = re.search(
                r'(\d+\s+[\w\s]+(?:street|st|avenue|ave|road|rd|blvd|boulevard|lane|ln|drive|dr|way|court|ct|place|pl|circle|viaduct|trail|parkway|highway|hwy))',
                line_text, re.IGNORECASE
            )
            if street_match:
                address = ExtractedAddress(
                    full_text=line_text,
                    street=street_match.group(1).strip(),
                    line_idx=line_idx,
                    confidence=0.5,
                )
        
        if address:
            addresses.append(address)
    
    return addresses


# Common city/state spelling mistakes for spell-checking
COMMON_SPELLING_MISTAKES = {
    # US Cities
    "los angles": "Los Angeles",
    "los angelas": "Los Angeles",
    "los angelus": "Los Angeles",
    "san fransisco": "San Francisco",
    "san fransico": "San Francisco",
    "philedelphia": "Philadelphia",
    "phildelphia": "Philadelphia",
    "pittsburg": "Pittsburgh",
    "cincinatti": "Cincinnati",
    "clevland": "Cleveland",
    "houstan": "Houston",
    "phoneix": "Phoenix",
    "atlenta": "Atlanta",
    "chicaco": "Chicago",
    "seatle": "Seattle",
    "seatttle": "Seattle",
    "portand": "Portland",
    "denvir": "Denver",
    "miame": "Miami",
    "minnapolis": "Minneapolis",
    "milwauke": "Milwaukee",
    "detriot": "Detroit",
    "balitmore": "Baltimore",
    "washingon": "Washington",
    "washinton": "Washington",
    "new yrok": "New York",
    "newyork": "New York",
    # US States
    "califronia": "California",
    "californai": "California",
    "calfornia": "California",
    "texis": "Texas",
    "florda": "Florida",
    "flordia": "Florida",
    "pensilvania": "Pennsylvania",
    "pensylvania": "Pennsylvania",
    "massachusets": "Massachusetts",
    "massachsetts": "Massachusetts",
    "conneticut": "Connecticut",
    "connecticutt": "Connecticut",
    "illanois": "Illinois",
    "illinios": "Illinois",
    "michagan": "Michigan",
    "virgina": "Virginia",
    "virgnia": "Virginia",
    "arizonia": "Arizona",
    "colorodo": "Colorado",
    "tennesee": "Tennessee",
    "tennesse": "Tennessee",
    "missisipi": "Mississippi",
    "missisippi": "Mississippi",
    # Indian Cities
    "bangalor": "Bangalore",
    "banglaore": "Bangalore",
    "bengalore": "Bengaluru",
    "mumbia": "Mumbai",
    "bombey": "Mumbai",
    "bombai": "Mumbai",
    "dehli": "Delhi",
    "dilli": "Delhi",
    "chenai": "Chennai",
    "madras": "Chennai",
    "kolkatta": "Kolkata",
    "calcuta": "Kolkata",
    "hyderbad": "Hyderabad",
    "hydrabad": "Hyderabad",
    "ahmedabd": "Ahmedabad",
    "ahmadabad": "Ahmedabad",
    # Indian States
    "maharastra": "Maharashtra",
    "maharashta": "Maharashtra",
    "karnatka": "Karnataka",
    "tamilnadu": "Tamil Nadu",
    "gujrat": "Gujarat",
    "rajastan": "Rajasthan",
    "rajastahn": "Rajasthan",
    "kerela": "Kerala",
    "karala": "Kerala",
    "panjab": "Punjab",
    "utter pradesh": "Uttar Pradesh",
    "uttar pradsh": "Uttar Pradesh",
}


def detect_spelling_errors(text: str) -> List[Dict[str, str]]:
    """
    Detect common spelling mistakes in city/state names.
    
    Returns:
        List of dicts with 'wrong' and 'correct' keys
    """
    errors = []
    text_lower = text.lower()
    
    for wrong, correct in COMMON_SPELLING_MISTAKES.items():
        if wrong in text_lower:
            errors.append({
                "wrong": wrong,
                "correct": correct,
                "context": text[:50]
            })
    
    return errors


def validate_us_zip_state(zip_code: str, state_code: str) -> Tuple[bool, str]:
    """
    Validate that a US ZIP code matches the expected state.
    
    Returns:
        Tuple of (is_valid, reason)
    """
    if not zip_code or not state_code:
        return True, "incomplete_data"
    
    zip_prefix = zip_code[:3]
    expected_state = US_ZIP_STATE_PREFIX.get(zip_prefix)
    
    if expected_state is None:
        return True, "unknown_prefix"  # Can't validate, assume OK
    
    if expected_state != state_code:
        return False, f"ZIP {zip_code} belongs to {expected_state}, not {state_code}"
    
    return True, "valid"


def validate_indian_pin_state(pin_code: str, state_name: Optional[str]) -> Tuple[bool, str]:
    """
    Validate that an Indian PIN code matches the expected state.
    """
    if not pin_code:
        return True, "incomplete_data"
    
    pin_prefix = pin_code[:2]
    expected_state_code = INDIAN_PIN_STATE.get(pin_prefix)
    
    if expected_state_code is None:
        return True, "unknown_prefix"
    
    if state_name:
        # Check if state name matches
        state_lower = state_name.lower()
        expected_state_name = INDIAN_STATES.get(expected_state_code, "").lower()
        
        if expected_state_name and expected_state_name not in state_lower and state_lower not in expected_state_name:
            return False, f"PIN {pin_code} belongs to {expected_state_name}, not {state_name}"
    
    return True, "valid"


def detect_address_anomalies(tokens: List[Any]) -> List[FraudSignal]:
    """
    Detect address-related fraud signals.
    
    Checks for:
    1. Invalid ZIP/postal code formats
    2. ZIP code to state mismatches
    3. Fake/placeholder addresses
    4. Mixed country indicators
    5. Missing or incomplete addresses
    """
    signals = []
    
    if not tokens:
        return signals
    
    # Extract addresses
    addresses = extract_addresses_from_tokens(tokens)
    
    if not addresses:
        # No addresses found - could be suspicious for invoices
        # But don't flag as we might just not have detected it
        return signals
    
    for addr in addresses:
        # Check for fake address patterns
        for pattern in FAKE_ADDRESS_PATTERNS:
            if re.search(pattern, addr.full_text.lower()):
                signals.append(FraudSignal(
                    signal_id="FAKE_ADDRESS_PATTERN",
                    severity="high",
                    confidence=0.85,
                    description=f"Address appears to be a fake/placeholder: '{addr.full_text[:50]}'",
                    evidence={
                        "address": addr.full_text,
                        "matched_pattern": pattern,
                    },
                    recommendation="Verify merchant address authenticity",
                ))
                break
        
        # Validate US ZIP to state
        if addr.country_code == "US" and addr.zip_code and addr.state_code:
            is_valid, reason = validate_us_zip_state(addr.zip_code, addr.state_code)
            if not is_valid:
                signals.append(FraudSignal(
                    signal_id="ZIP_STATE_MISMATCH",
                    severity="critical",  # Escalated to CRITICAL - strong fraud indicator
                    confidence=0.95,
                    description=f"ZIP code doesn't match state: {reason}",
                    evidence={
                        "zip_code": addr.zip_code,
                        "state": addr.state_code,
                        "expected_state": reason,
                    },
                    recommendation="ADDRESS FABRICATED - ZIP code belongs to different state. Requires mandatory review.",
                ))
        
        # Validate Indian PIN to state
        if addr.country_code == "IN" and addr.zip_code:
            is_valid, reason = validate_indian_pin_state(addr.zip_code, addr.state)
            if not is_valid:
                signals.append(FraudSignal(
                    signal_id="PIN_STATE_MISMATCH",
                    severity="critical",  # Escalated to CRITICAL - strong fraud indicator
                    confidence=0.95,
                    description=f"PIN code doesn't match state: {reason}",
                    evidence={
                        "pin_code": addr.zip_code,
                        "state": addr.state,
                    },
                    recommendation="ADDRESS FABRICATED - PIN code belongs to different state. Requires mandatory review.",
                ))
        
        # Check for invalid ZIP format
        if addr.zip_code:
            if addr.country_code == "US":
                if not re.match(r'^\d{5}(-\d{4})?$', addr.zip_code):
                    signals.append(FraudSignal(
                        signal_id="INVALID_ZIP_FORMAT",
                        severity="medium",
                        confidence=0.7,
                        description=f"Invalid US ZIP code format: '{addr.zip_code}'",
                        evidence={"zip_code": addr.zip_code},
                        recommendation="Verify ZIP code format",
                    ))
            elif addr.country_code == "IN":
                if not re.match(r'^\d{6}$', addr.zip_code):
                    signals.append(FraudSignal(
                        signal_id="INVALID_PIN_FORMAT",
                        severity="medium",
                        confidence=0.7,
                        description=f"Invalid Indian PIN code format: '{addr.zip_code}'",
                        evidence={"pin_code": addr.zip_code},
                        recommendation="Verify PIN code format",
                    ))
        
        # Check for suspicious ZIP codes (all same digits, sequential)
        if addr.zip_code:
            clean_zip = addr.zip_code.replace("-", "").replace(" ", "")
            if len(set(clean_zip)) == 1:  # All same digits like 11111, 00000
                signals.append(FraudSignal(
                    signal_id="SUSPICIOUS_ZIP_CODE",
                    severity="high",
                    confidence=0.8,
                    description=f"ZIP/PIN code has suspicious pattern (all same digits): '{addr.zip_code}'",
                    evidence={"zip_code": addr.zip_code},
                    recommendation="Likely placeholder - verify address",
                ))
            elif clean_zip in ["12345", "123456", "54321", "654321", "00000", "000000", "99999", "999999"]:
                signals.append(FraudSignal(
                    signal_id="PLACEHOLDER_ZIP_CODE",
                    severity="high",
                    confidence=0.9,
                    description=f"ZIP/PIN code appears to be a placeholder: '{addr.zip_code}'",
                    evidence={"zip_code": addr.zip_code},
                    recommendation="Fake address - common placeholder ZIP code",
                ))
    
    # Check for mixed country indicators
    countries_found = set(addr.country_code for addr in addresses if addr.country_code)
    if len(countries_found) > 1:
        # Multiple countries in same document could be legitimate (international trade)
        # But check if same "address block" has mixed indicators
        pass  # Don't flag for now
    
    # Check for spelling errors in addresses
    for addr in addresses:
        spelling_errors = detect_spelling_errors(addr.full_text)
        if spelling_errors:
            signals.append(FraudSignal(
                signal_id="ADDRESS_SPELLING_ERRORS",
                severity="high",
                confidence=0.85,
                description=f"Address contains spelling errors: {', '.join(e['wrong'] for e in spelling_errors)}",
                evidence={
                    "address": addr.full_text,
                    "spelling_errors": spelling_errors,
                    "corrections": {e['wrong']: e['correct'] for e in spelling_errors},
                },
                recommendation=f"POSSIBLE FAKE ADDRESS - Misspelled: {spelling_errors[0]['wrong']} (should be '{spelling_errors[0]['correct']}')",
            ))
    
    return signals


def run_fraud_detection(
    tokens: List[Any],
    merchant: Optional[str] = None,
    total: Optional[float] = None,
    subtotal: Optional[float] = None,
    tax: Optional[float] = None,
    tax_rate: Optional[float] = None,
    items_sum: Optional[float] = None,
    receipt_date: Optional[str] = None,
    page_width: float = 612,
    page_height: float = 792,
) -> Dict[str, Any]:
    """
    Run comprehensive fraud detection on a document.
    
    Returns:
        Dict with signals, risk_score, risk_level, and summary.
    """
    all_signals = []
    
    # Amount anomalies
    all_signals.extend(detect_amount_anomalies(
        total=total, subtotal=subtotal, tax=tax,
        tax_rate=tax_rate, items_sum=items_sum,
    ))
    
    # Layout anomalies
    all_signals.extend(detect_layout_anomalies(
        tokens=tokens, page_width=page_width, page_height=page_height,
    ))
    
    # Content anomalies
    all_signals.extend(detect_content_anomalies(
        tokens=tokens, merchant=merchant, total=total, receipt_date=receipt_date,
    ))
    
    # Address anomalies
    all_signals.extend(detect_address_anomalies(tokens=tokens))
    
    # Font inconsistencies (geometry-based detection)
    all_signals.extend(detect_font_inconsistencies(tokens=tokens))
    
    # Calculate risk score
    severity_weights = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.15}
    
    if all_signals:
        weighted_scores = [
            severity_weights.get(s.severity, 0.3) * s.confidence
            for s in all_signals
        ]
        risk_score = min(1.0, sum(weighted_scores) / len(weighted_scores) + len(weighted_scores) * 0.05)
    else:
        risk_score = 0.0
    
    # Determine risk level
    if risk_score >= 0.7:
        risk_level = "critical"
    elif risk_score >= 0.5:
        risk_level = "high"
    elif risk_score >= 0.25:
        risk_level = "medium"
    else:
        risk_level = "low"
    
    # Build summary
    if all_signals:
        critical_count = sum(1 for s in all_signals if s.severity == "critical")
        high_count = sum(1 for s in all_signals if s.severity == "high")
        summary = f"{len(all_signals)} signals detected"
        if critical_count:
            summary += f" ({critical_count} critical)"
        elif high_count:
            summary += f" ({high_count} high severity)"
    else:
        summary = "No anomalies detected"
    
    return {
        "signals": [
            {
                "signal_id": s.signal_id,
                "severity": s.severity,
                "confidence": s.confidence,
                "description": s.description,
                "evidence": s.evidence,
                "recommendation": s.recommendation,
            }
            for s in all_signals
        ],
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level,
        "summary": summary,
        "signal_count": len(all_signals),
    }
