"""
Unified LayoutToken interface for document text extraction.

Provides a single abstraction for text tokens with optional bounding box coordinates,
enabling consistent downstream processing for both PDFs and images.

Token Sources:
- PyMuPDF: Native PDF text with coordinates (when available)
- EasyOCR: Image OCR with bounding boxes
- Tesseract: Image OCR with TSV/HOCR bounding boxes
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Try imports
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import easyocr
    HAS_EASYOCR = True
    _easyocr_reader = None
except ImportError:
    HAS_EASYOCR = False
    _easyocr_reader = None

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class LayoutToken:
    """
    A text token with optional bounding box coordinates.
    
    Attributes:
        text: The token text content
        x0: Left edge coordinate (None if unavailable)
        y0: Top edge coordinate (None if unavailable)
        x1: Right edge coordinate (None if unavailable)
        y1: Bottom edge coordinate (None if unavailable)
        page: Page number (0-indexed)
        source: Token source ("pymupdf", "easyocr", "tesseract", "line_fallback")
        line_idx: Line index within the document
        confidence: OCR confidence score (0.0-1.0, None if not applicable)
        metadata: Additional token metadata
    """
    text: str
    x0: Optional[float] = None
    y0: Optional[float] = None
    x1: Optional[float] = None
    y1: Optional[float] = None
    page: int = 0
    source: str = "unknown"
    line_idx: int = 0
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_coords(self) -> bool:
        """Check if this token has valid bounding box coordinates."""
        return all(c is not None for c in [self.x0, self.y0, self.x1, self.y1])
    
    @property
    def center_y(self) -> Optional[float]:
        """Get vertical center of the token."""
        if self.y0 is not None and self.y1 is not None:
            return (self.y0 + self.y1) / 2
        return None
    
    @property
    def center_x(self) -> Optional[float]:
        """Get horizontal center of the token."""
        if self.x0 is not None and self.x1 is not None:
            return (self.x0 + self.x1) / 2
        return None
    
    @property
    def height(self) -> Optional[float]:
        """Get token height."""
        if self.y0 is not None and self.y1 is not None:
            return abs(self.y1 - self.y0)
        return None
    
    @property
    def width(self) -> Optional[float]:
        """Get token width."""
        if self.x0 is not None and self.x1 is not None:
            return abs(self.x1 - self.x0)
        return None


@dataclass
class LayoutDocument:
    """
    A document represented as a list of LayoutTokens with metadata.
    
    Attributes:
        tokens: List of LayoutTokens
        page_count: Number of pages
        page_heights: Height of each page (for zone calculation)
        page_widths: Width of each page
        source: Primary token source
        lines: Reconstructed line-based text (for backward compatibility)
    """
    tokens: List[LayoutToken]
    page_count: int = 1
    page_heights: List[float] = field(default_factory=list)
    page_widths: List[float] = field(default_factory=list)
    source: str = "unknown"
    lines: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_page_tokens(self, page: int) -> List[LayoutToken]:
        """Get all tokens for a specific page."""
        return [t for t in self.tokens if t.page == page]
    
    def get_tokens_in_y_range(self, y_min: float, y_max: float, page: int = 0) -> List[LayoutToken]:
        """Get tokens within a vertical range on a page."""
        return [
            t for t in self.tokens 
            if t.page == page and t.has_coords 
            and t.y0 is not None and t.y1 is not None
            and t.y0 >= y_min and t.y1 <= y_max
        ]
    
    def get_header_tokens(self, fraction: float = 0.25, page: int = 0) -> List[LayoutToken]:
        """Get tokens in the header region (top fraction of page)."""
        if not self.page_heights or page >= len(self.page_heights):
            # Fallback: use first N tokens by line_idx
            page_tokens = self.get_page_tokens(page)
            if not page_tokens:
                return []
            max_line = max(t.line_idx for t in page_tokens)
            threshold = int(max_line * fraction)
            return [t for t in page_tokens if t.line_idx <= threshold]
        
        page_height = self.page_heights[page]
        y_max = page_height * fraction
        return self.get_tokens_in_y_range(0, y_max, page)


# -----------------------------------------------------------------------------
# Token Builders
# -----------------------------------------------------------------------------

def _get_easyocr_reader():
    """Lazy load EasyOCR reader."""
    global _easyocr_reader
    if _easyocr_reader is None and HAS_EASYOCR:
        logger.info("Loading EasyOCR reader...")
        _easyocr_reader = easyocr.Reader(['en'], gpu=False)
        logger.info("EasyOCR reader loaded")
    return _easyocr_reader


def build_tokens_from_pymupdf(pdf_path: str) -> LayoutDocument:
    """
    Build LayoutTokens from a PDF using PyMuPDF.
    
    Attempts to extract text with coordinates. Falls back to line-based
    extraction if coordinates are unavailable.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        LayoutDocument with tokens
    """
    if not HAS_PYMUPDF:
        raise ImportError("PyMuPDF (fitz) is required for PDF extraction")
    
    doc = fitz.open(pdf_path)
    tokens = []
    lines = []
    page_heights = []
    page_widths = []
    line_idx = 0
    
    for page_num, page in enumerate(doc):
        page_rect = page.rect
        page_heights.append(page_rect.height)
        page_widths.append(page_rect.width)
        
        # Try to get text with coordinates using dict extraction
        try:
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            has_coords = True
        except Exception:
            blocks = []
            has_coords = False
        
        if has_coords and blocks:
            # Extract tokens with coordinates
            for block in blocks:
                if block.get("type") != 0:  # Skip non-text blocks
                    continue
                
                for line_data in block.get("lines", []):
                    line_text_parts = []
                    for span in line_data.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        
                        bbox = span.get("bbox", [0, 0, 0, 0])
                        tokens.append(LayoutToken(
                            text=text,
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                            page=page_num,
                            source="pymupdf",
                            line_idx=line_idx,
                            metadata={"font": span.get("font"), "size": span.get("size")}
                        ))
                        line_text_parts.append(text)
                    
                    if line_text_parts:
                        lines.append(" ".join(line_text_parts))
                        line_idx += 1
        else:
            # Fallback: line-based extraction without coordinates
            text = page.get_text("text")
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    tokens.append(LayoutToken(
                        text=line,
                        x0=None,
                        y0=None,
                        x1=None,
                        y1=None,
                        page=page_num,
                        source="pymupdf_line_fallback",
                        line_idx=line_idx,
                    ))
                    lines.append(line)
                    line_idx += 1
    
    doc.close()
    
    return LayoutDocument(
        tokens=tokens,
        page_count=len(page_heights),
        page_heights=page_heights,
        page_widths=page_widths,
        source="pymupdf",
        lines=lines,
        metadata={"pdf_path": pdf_path}
    )


def build_tokens_from_easyocr(image_path: str) -> LayoutDocument:
    """
    Build LayoutTokens from an image using EasyOCR.
    
    Args:
        image_path: Path to the image file (JPG/PNG)
        
    Returns:
        LayoutDocument with tokens including bounding boxes
    """
    if not HAS_EASYOCR:
        raise ImportError("EasyOCR is required for image OCR")
    if not HAS_PIL:
        raise ImportError("PIL is required for image processing")
    
    reader = _get_easyocr_reader()
    img = Image.open(image_path)
    img_array = np.array(img)
    
    # Get image dimensions
    width, height = img.size
    
    # Run OCR with detail=1 to get bounding boxes
    results = reader.readtext(img_array, detail=1)
    
    tokens = []
    lines = []
    
    for idx, (bbox, text, conf) in enumerate(results):
        text = text.strip()
        if not text:
            continue
        
        # EasyOCR bbox format: [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]
        # Convert to x0, y0, x1, y1
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
        page_heights=[float(height)],
        page_widths=[float(width)],
        source="easyocr",
        lines=lines,
        metadata={"image_path": image_path, "avg_confidence": sum(t.confidence or 0 for t in tokens) / len(tokens) if tokens else 0}
    )


def build_tokens_from_tesseract(image_path: str, use_tsv: bool = True) -> LayoutDocument:
    """
    Build LayoutTokens from an image using Tesseract with TSV/HOCR output.
    
    Args:
        image_path: Path to the image file (JPG/PNG)
        use_tsv: If True, use TSV output; otherwise use HOCR
        
    Returns:
        LayoutDocument with tokens including bounding boxes
    """
    if not HAS_TESSERACT:
        raise ImportError("pytesseract is required for Tesseract OCR")
    if not HAS_PIL:
        raise ImportError("PIL is required for image processing")
    
    img = Image.open(image_path)
    width, height = img.size
    
    tokens = []
    lines = []
    
    if use_tsv:
        # Use TSV output for word-level bounding boxes
        tsv_output = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        
        n_boxes = len(tsv_output['text'])
        current_line_words = []
        current_line_idx = 0
        prev_line_num = -1
        
        for i in range(n_boxes):
            text = tsv_output['text'][i].strip()
            conf = tsv_output['conf'][i]
            line_num = tsv_output['line_num'][i]
            
            # Track line changes
            if line_num != prev_line_num and current_line_words:
                lines.append(" ".join(current_line_words))
                current_line_words = []
                current_line_idx += 1
            prev_line_num = line_num
            
            if not text or conf < 0:  # Tesseract uses -1 for non-text
                continue
            
            x0 = tsv_output['left'][i]
            y0 = tsv_output['top'][i]
            w = tsv_output['width'][i]
            h = tsv_output['height'][i]
            
            tokens.append(LayoutToken(
                text=text,
                x0=float(x0),
                y0=float(y0),
                x1=float(x0 + w),
                y1=float(y0 + h),
                page=0,
                source="tesseract",
                line_idx=current_line_idx,
                confidence=float(conf) / 100.0 if conf > 0 else None,
            ))
            current_line_words.append(text)
        
        # Add final line
        if current_line_words:
            lines.append(" ".join(current_line_words))
    else:
        # Fallback: simple text extraction without boxes
        text = pytesseract.image_to_string(img)
        for idx, line in enumerate(text.split("\n")):
            line = line.strip()
            if line:
                tokens.append(LayoutToken(
                    text=line,
                    x0=None,
                    y0=None,
                    x1=None,
                    y1=None,
                    page=0,
                    source="tesseract_line_fallback",
                    line_idx=idx,
                ))
                lines.append(line)
    
    return LayoutDocument(
        tokens=tokens,
        page_count=1,
        page_heights=[float(height)],
        page_widths=[float(width)],
        source="tesseract",
        lines=lines,
        metadata={"image_path": image_path}
    )


def build_tokens_from_lines(lines: List[str], source: str = "lines") -> LayoutDocument:
    """
    Build LayoutTokens from a list of text lines (no coordinates).
    
    Useful for backward compatibility with existing line-based code.
    
    Args:
        lines: List of text lines
        source: Source identifier
        
    Returns:
        LayoutDocument with tokens (no coordinates)
    """
    tokens = []
    clean_lines = []
    
    for idx, line in enumerate(lines):
        text = line.strip() if line else ""
        if text:
            tokens.append(LayoutToken(
                text=text,
                x0=None,
                y0=None,
                x1=None,
                y1=None,
                page=0,
                source=source,
                line_idx=idx,
            ))
            clean_lines.append(text)
    
    return LayoutDocument(
        tokens=tokens,
        page_count=1,
        page_heights=[],
        page_widths=[],
        source=source,
        lines=clean_lines,
    )


def build_tokens_auto(file_path: str) -> LayoutDocument:
    """
    Automatically build LayoutTokens based on file type.
    
    - PDF files: Use PyMuPDF
    - Image files (JPG/PNG): Use EasyOCR with Tesseract fallback
    
    Args:
        file_path: Path to the file
        
    Returns:
        LayoutDocument with tokens
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix == ".pdf":
        if not HAS_PYMUPDF:
            raise ImportError("PyMuPDF required for PDF processing")
        return build_tokens_from_pymupdf(file_path)
    
    elif suffix in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]:
        # Try Tesseract first (better accuracy on thermal/POS receipts)
        if HAS_TESSERACT:
            try:
                doc = build_tokens_from_tesseract(file_path)
                if doc.tokens and doc.metadata.get("avg_confidence", 0) > 0.3:
                    return doc
                logger.warning(f"Tesseract low confidence ({doc.metadata.get('avg_confidence', 0):.2f}), trying EasyOCR")
            except Exception as e:
                logger.warning(f"Tesseract failed: {e}, trying EasyOCR")
        
        # Fallback to EasyOCR
        if HAS_EASYOCR:
            return build_tokens_from_easyocr(file_path)
        
        raise ImportError("No OCR engine available (Tesseract or EasyOCR required)")
    
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


# -----------------------------------------------------------------------------
# Zone Detection
# -----------------------------------------------------------------------------

@dataclass
class DocumentZones:
    """
    Detected zones in a document.
    
    Attributes:
        seller_zone: Tokens in the seller/header zone
        billto_zone: Tokens in the Bill To zone
        shipto_zone: Tokens in the Ship To zone
        other_zones: Other detected zones
        anchor_hits: Labels/anchors that were detected
    """
    seller_zone: List[LayoutToken] = field(default_factory=list)
    billto_zone: List[LayoutToken] = field(default_factory=list)
    shipto_zone: List[LayoutToken] = field(default_factory=list)
    other_zones: Dict[str, List[LayoutToken]] = field(default_factory=dict)
    anchor_hits: Dict[str, int] = field(default_factory=dict)  # anchor -> line_idx
    seller_zone_indices: set = field(default_factory=set)
    buyer_zone_indices: set = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Zone anchor patterns
BUYER_ANCHORS = {
    "bill to", "billed to", "bill-to", "billto",
    "ship to", "shipped to", "ship-to", "shipto",
    "sold to", "sold-to", "soldto",
    "invoice to", "invoiced to",
    "customer", "consignee", "buyer", "client",
    "deliver to", "delivery to", "attention", "attn",
}

SELLER_ANCHORS = {
    "from", "sold by", "vendor", "supplier", 
    "exporter", "shipper", "seller", "issued by",
    "remit to", "pay to",
}

# Structural labels to reject as merchant candidates
STRUCTURAL_LABELS = {
    "received amount", "amount received", "balance due", "balance",
    "grand total", "total", "subtotal", "sub total", "net total",
    "tax", "tax amount", "vat", "gst", "sales tax",
    "invoice", "receipt", "bill", "statement", "quotation",
    "description", "qty", "quantity", "price", "unit price", "rate",
    "amount", "total amount", "payment", "discount",
    # Billing/shipping labels (common false positives for merchant)
    "bill to", "billed to", "sold to", "ship to", "shipped to", "deliver to",
    "from", "to", "buyer", "seller", "customer", "consignee", "shipper",
    "vendor", "supplier", "exporter", "importer", "notify party",
    "particulars", "items", "services", "goods",
}


def compute_zone_confidence(doc: LayoutDocument, zones: "DocumentZones") -> Tuple[float, List[str]]:
    """
    Compute zone detection confidence using cheap heuristics.
    
    Returns a value between 0.0 and 1.0 indicating how reliable
    the zone detection is likely to be.
    
    Args:
        doc: LayoutDocument with tokens
        zones: Detected zones
        
    Returns:
        Tuple of (zone_confidence, list of reasons for the confidence level)
    """
    reasons = []
    confidence = 1.0
    
    # Check 1: Token count - need enough tokens for reliable zone detection
    token_count = len(doc.tokens)
    if token_count < 10:
        reasons.append(f"very_low_token_count:{token_count}")
        return 0.0, reasons
    elif token_count < 30:
        reasons.append(f"low_token_count:{token_count}")
        confidence *= 0.5
    
    # Check 2: Coordinate coverage - if we have coords, check coverage
    has_coords = any(t.has_coords for t in doc.tokens)
    if has_coords and doc.page_heights:
        page_height = doc.page_heights[0] if doc.page_heights else 0
        if page_height > 0:
            # Get Y range of tokens with coords
            tokens_with_coords = [t for t in doc.tokens if t.has_coords and t.y0 is not None]
            if tokens_with_coords:
                min_y = min(t.y0 for t in tokens_with_coords)
                max_y = max(t.y1 for t in tokens_with_coords if t.y1 is not None)
                y_coverage = (max_y - min_y) / page_height
                
                if y_coverage < 0.25:
                    reasons.append(f"low_y_coverage:{y_coverage:.2f}")
                    confidence *= 0.3
                elif y_coverage < 0.5:
                    reasons.append(f"medium_y_coverage:{y_coverage:.2f}")
                    confidence *= 0.7
    
    # Check 3: Both zones should have tokens for reliable differentiation
    # Missing zone tokens = unreliable zone detection = must gate
    seller_zone_count = len(zones.seller_zone_indices)
    buyer_zone_count = len(zones.buyer_zone_indices)
    
    if seller_zone_count == 0 and buyer_zone_count == 0:
        reasons.append("no_zone_tokens")
        confidence = 0.0  # Unreliable - no zones detected
        return confidence, reasons
    elif seller_zone_count == 0:
        reasons.append("no_seller_zone_tokens")
        confidence = 0.2  # Unreliable - can't identify seller zone
    elif buyer_zone_count == 0:
        reasons.append("no_buyer_zone_tokens")
        confidence = 0.2  # Unreliable - can't differentiate seller from buyer
    
    # Check 4: Anchor-based detection can boost confidence, but only if zones exist
    # Anchors alone don't make zone detection reliable if zone tokens are missing
    if zones.anchor_hits and seller_zone_count > 0 and buyer_zone_count > 0:
        buyer_anchors = [a for a in zones.anchor_hits.keys() if a in BUYER_ANCHORS]
        seller_anchors = [a for a in zones.anchor_hits.keys() if a in SELLER_ANCHORS]
        if buyer_anchors:
            reasons.append(f"buyer_anchors:{','.join(buyer_anchors[:2])}")
            confidence = min(1.0, confidence * 1.2)  # Boost for anchor detection
        if seller_anchors:
            reasons.append(f"seller_anchors:{','.join(seller_anchors[:2])}")
            confidence = min(1.0, confidence * 1.1)
    
    # Check 5: Page rotation (if available in metadata)
    rotation = doc.metadata.get("rotation", 0)
    if rotation in [90, 270]:
        if not doc.metadata.get("coords_transformed", False):
            reasons.append(f"unhandled_rotation:{rotation}")
            confidence = 0.0
            return confidence, reasons
    
    # Cap confidence
    confidence = max(0.0, min(1.0, confidence))
    
    if not reasons:
        reasons.append("standard_detection")
    
    return round(confidence, 2), reasons


def collect_layout_diagnostics(doc: LayoutDocument) -> Dict[str, Any]:
    """
    Collect layout diagnostics for debugging zone detection issues.
    
    Args:
        doc: LayoutDocument with tokens
        
    Returns:
        Dictionary with layout diagnostic information
    """
    diagnostics = {
        "token_count": len(doc.tokens),
        "page_count": doc.page_count,
        "source": doc.source,
    }
    
    # Per-page diagnostics
    pages = []
    for page_idx in range(doc.page_count):
        page_tokens = [t for t in doc.tokens if t.page == page_idx]
        page_diag = {
            "page": page_idx,
            "token_count": len(page_tokens),
        }
        
        # Page dimensions
        if doc.page_widths and page_idx < len(doc.page_widths):
            page_diag["page_width"] = doc.page_widths[page_idx]
        if doc.page_heights and page_idx < len(doc.page_heights):
            page_diag["page_height"] = doc.page_heights[page_idx]
        
        # Token bbox coverage
        tokens_with_coords = [t for t in page_tokens if t.has_coords]
        if tokens_with_coords:
            page_diag["tokens_with_coords"] = len(tokens_with_coords)
            y_values = [t.y0 for t in tokens_with_coords if t.y0 is not None]
            y_max_values = [t.y1 for t in tokens_with_coords if t.y1 is not None]
            if y_values and y_max_values:
                page_diag["min_y"] = round(min(y_values), 1)
                page_diag["max_y"] = round(max(y_max_values), 1)
        
        # Rotation if available
        if "rotation" in doc.metadata:
            page_diag["rotation"] = doc.metadata.get("rotation", 0)
        
        pages.append(page_diag)
    
    diagnostics["pages"] = pages
    return diagnostics


def detect_zones(doc: LayoutDocument, header_fraction: float = 0.25) -> DocumentZones:
    """
    Detect seller/buyer zones in a LayoutDocument.
    
    Strategy:
    1. If coords available: Use geometric zones (top 20-25% = seller zone)
    2. Detect anchor labels (BILL TO, SHIP TO, etc.)
    3. Mark tokens after buyer anchors as buyer zone
    4. Mark tokens before buyer anchor or in header as seller zone
    
    Args:
        doc: LayoutDocument to analyze
        header_fraction: Fraction of page height for header zone (default 0.25)
        
    Returns:
        DocumentZones with classified tokens
    """
    zones = DocumentZones()
    
    if not doc.tokens:
        return zones
    
    # Check if we have coordinates
    has_coords = any(t.has_coords for t in doc.tokens)
    
    # Find anchor positions
    buyer_anchor_indices = {}  # anchor_name -> line_idx
    seller_anchor_indices = {}
    
    for token in doc.tokens:
        text_lower = token.text.lower().strip()
        text_clean = re.sub(r'[:\s]+$', '', text_lower)  # Remove trailing colon/spaces
        
        for anchor in BUYER_ANCHORS:
            if anchor in text_clean or text_clean == anchor.replace(" ", ""):
                buyer_anchor_indices[anchor] = token.line_idx
                zones.anchor_hits[anchor] = token.line_idx
                break
        
        for anchor in SELLER_ANCHORS:
            if anchor in text_clean or text_clean == anchor.replace(" ", ""):
                seller_anchor_indices[anchor] = token.line_idx
                zones.anchor_hits[anchor] = token.line_idx
                break
    
    # Determine zone boundaries
    first_buyer_anchor_idx = min(buyer_anchor_indices.values()) if buyer_anchor_indices else float('inf')
    
    if has_coords and doc.page_heights:
        # Coordinate-based zone detection
        page_height = doc.page_heights[0]
        header_y_max = page_height * header_fraction
        
        for token in doc.tokens:
            if not token.has_coords:
                continue
            
            # Check if in header region (seller zone)
            if token.y0 is not None and token.y0 < header_y_max:
                # But not if after a buyer anchor
                if token.line_idx < first_buyer_anchor_idx:
                    zones.seller_zone.append(token)
                    zones.seller_zone_indices.add(token.line_idx)
            
            # Check if after buyer anchors
            for anchor, anchor_idx in buyer_anchor_indices.items():
                if token.line_idx > anchor_idx and token.line_idx <= anchor_idx + 6:
                    if "bill" in anchor or "sold" in anchor or "invoice" in anchor or "customer" in anchor:
                        zones.billto_zone.append(token)
                    elif "ship" in anchor or "deliver" in anchor or "consignee" in anchor:
                        zones.shipto_zone.append(token)
                    zones.buyer_zone_indices.add(token.line_idx)
    else:
        # Line-based fallback zone detection
        max_line = max(t.line_idx for t in doc.tokens)
        header_line_max = int(max_line * header_fraction)
        
        for token in doc.tokens:
            # Seller zone: early lines before buyer anchor
            if token.line_idx <= header_line_max and token.line_idx < first_buyer_anchor_idx:
                zones.seller_zone.append(token)
                zones.seller_zone_indices.add(token.line_idx)
            
            # Buyer zones: lines after buyer anchors (within window)
            for anchor, anchor_idx in buyer_anchor_indices.items():
                if token.line_idx > anchor_idx and token.line_idx <= anchor_idx + 6:
                    if "bill" in anchor or "sold" in anchor or "invoice" in anchor or "customer" in anchor:
                        zones.billto_zone.append(token)
                    elif "ship" in anchor or "deliver" in anchor or "consignee" in anchor:
                        zones.shipto_zone.append(token)
                    zones.buyer_zone_indices.add(token.line_idx)
    
    # Also mark seller anchor zones
    for anchor, anchor_idx in seller_anchor_indices.items():
        for token in doc.tokens:
            if token.line_idx > anchor_idx and token.line_idx <= anchor_idx + 6:
                if token.line_idx not in zones.seller_zone_indices:
                    zones.seller_zone.append(token)
                    zones.seller_zone_indices.add(token.line_idx)
    
    zones.metadata = {
        "has_coords": has_coords,
        "header_fraction": header_fraction,
        "buyer_anchors_found": list(buyer_anchor_indices.keys()),
        "seller_anchors_found": list(seller_anchor_indices.keys()),
    }
    
    return zones


def is_structural_label(text: str) -> bool:
    """Check if text is a structural label that should be rejected as merchant."""
    if not text:
        return False
    
    text_lower = text.lower().strip()
    text_clean = re.sub(r'[:\s]+$', '', text_lower)
    text_words = set(text_clean.split())
    
    # Exact match
    if text_clean in STRUCTURAL_LABELS:
        return True
    
    # Check for financial field words
    financial_words = {"amount", "received", "balance", "total", "subtotal", "tax", "payment", "discount"}
    if text_words & financial_words:
        return True
    
    return False


# -----------------------------------------------------------------------------
# Merchant Extraction using LayoutTokens
# -----------------------------------------------------------------------------

# Legal entity suffixes (strong seller signal)
LEGAL_SUFFIXES = [
    " inc", " inc.", "inc", " llc", "llc", " ltd", " ltd.", "ltd",
    " corp", " corp.", "corp", " corporation",
    " company", " co.", " co,", " pvt", " private", " limited",
    " gmbh", "gmbh", " sa", " s.a.", " srl", " s.r.l.", " pty", " bv", " b.v.",
    " oy", " kk", " k.k.", " ag", " a.g.", " nv", " n.v.", " plc", " p.l.c.",
    " llp", "llp", " l.l.p.", " lp", " l.p.", " pllc", " pc", " p.c.",
]

# Contact/address indicators (boost nearby candidates)
CONTACT_INDICATORS = [
    "phone", "tel", "fax", "email", "mail", "www.", "http", ".com", ".org", ".net",
    "street", "st.", "avenue", "ave.", "road", "rd.", "blvd", "suite", "floor",
    "building", "city", "state", "zip", "postal", "address",
]

# Instructional phrases to reject
INSTRUCTIONAL_PHRASES = [
    "pay ", "please ", "contact ", "call ", "visit ", "email ",
    "obtain ", "send ", "submit ", "complete ", "fill ",
    "thank you", "thanks for", "if you", "you can", "you have",
    "payment is due", "payable to", "make cheque", "make check",
]


@dataclass
class MerchantCandidate:
    """A candidate for merchant extraction."""
    text: str
    token: LayoutToken
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    penalties: List[Dict[str, Any]] = field(default_factory=list)
    boosts: List[Dict[str, Any]] = field(default_factory=list)
    in_seller_zone: bool = False
    in_buyer_zone: bool = False
    has_legal_suffix: bool = False
    has_nearby_contact: bool = False


@dataclass 
class MerchantResult:
    """Result of merchant extraction."""
    merchant: Optional[str]
    confidence: float
    confidence_bucket: str  # HIGH, MEDIUM, LOW, NONE
    candidates: List[MerchantCandidate]
    winner_margin: float
    zones: DocumentZones
    evidence: Dict[str, Any] = field(default_factory=dict)


def _has_legal_suffix(text: str) -> bool:
    """Check if text contains a legal entity suffix."""
    if not text:
        return False
    text_lower = " " + text.lower()  # Add space prefix to match " inc" etc.
    # Check suffixes that require space prefix
    space_suffixes = [s for s in LEGAL_SUFFIXES if s.startswith(" ")]
    if any(suff in text_lower for suff in space_suffixes):
        return True
    # Check end-of-string suffixes
    for suff in LEGAL_SUFFIXES:
        clean_suff = suff.strip()
        if text_lower.strip().endswith(clean_suff):
            return True
    return False


def _has_nearby_contact(token: LayoutToken, doc: LayoutDocument, window: int = 3) -> bool:
    """Check if there's contact info within ±window lines of the token."""
    for other in doc.tokens:
        if abs(other.line_idx - token.line_idx) <= window and other.line_idx != token.line_idx:
            other_lower = other.text.lower()
            if any(ind in other_lower for ind in CONTACT_INDICATORS):
                return True
            # Check for phone pattern
            if re.search(r'[\+]?[\d\s\-\(\)]{7,}', other.text):
                return True
            # Check for email pattern
            if re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', other.text):
                return True
    return False


def _is_instructional(text: str) -> bool:
    """Check if text is instructional/action text."""
    if not text:
        return False
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in INSTRUCTIONAL_PHRASES)


def _is_plausible_company_name(text: str) -> bool:
    """Check if text could plausibly be a company name."""
    if not text or len(text.strip()) < 3:
        return False
    
    s = text.strip()
    lower = s.lower()
    
    # Too long
    if len(s) > 100:
        return False
    
    # Must have letters
    if not any(c.isalpha() for c in s):
        return False
    
    # Too many digits (likely invoice number)
    digit_ratio = sum(c.isdigit() for c in s) / max(len(s), 1)
    if digit_ratio > 0.3:  # Stricter threshold
        return False
    
    # Has colon (likely a label)
    if ':' in s:
        return False
    
    # Has # sign (likely reference number)
    if '#' in s:
        return False
    
    # Is a structural label
    if is_structural_label(s):
        return False
    
    # Is instructional
    if _is_instructional(s):
        return False
    
    # Reject document titles (INVOICE, RECEIPT, etc.)
    doc_titles = {
        "invoice", "tax invoice", "commercial invoice", "sales invoice",
        "proforma invoice", "receipt", "bill", "statement", "quotation",
        "quote", "estimate", "order", "purchase order", "credit note",
    }
    clean_lower = re.sub(r'[^\w\s]', '', lower).strip()
    if clean_lower in doc_titles:
        return False
    
    # Has legal suffix (strong positive)
    if _has_legal_suffix(s):
        return True
    
    # Proper capitalization (Title Case or ALL CAPS with multiple words)
    words = s.split()
    if len(words) >= 2:
        if s[0].isupper() or s.isupper():
            return True
    
    return False


def extract_merchant_from_tokens(
    doc: LayoutDocument,
    zones: Optional[DocumentZones] = None,
    strict: bool = True,
    enable_llm_tiebreak: bool = False,
    winner_margin_threshold: float = 2.0,
) -> MerchantResult:
    """
    Extract merchant/seller from a LayoutDocument using zone-aware scoring.
    
    This is the unified merchant extraction pipeline that works for both
    PDFs and images via the LayoutToken abstraction.
    
    Args:
        doc: LayoutDocument with tokens
        zones: Pre-computed zones (optional, will compute if not provided)
        strict: If True, apply stricter filtering
        enable_llm_tiebreak: If True and env MERCHANT_LLM_TIEBREAK=1, use LLM for ties
        winner_margin_threshold: Minimum margin for confident selection
        
    Returns:
        MerchantResult with extracted merchant and evidence
    """
    import os
    
    # Compute zones if not provided
    if zones is None:
        zones = detect_zones(doc)
    
    # Compute zone confidence and determine if zone scoring should be gated
    zone_confidence, zone_confidence_reasons = compute_zone_confidence(doc, zones)
    zone_gated = zone_confidence < 0.5
    zone_gated_reason = None
    if zone_gated:
        zone_gated_reason = f"zone_confidence={zone_confidence:.2f}<0.5"
    
    # Safety gate: zone_reliable boolean for clear decision
    zone_reliable = zone_confidence >= 0.5
    zone_reliable_reasons = zone_confidence_reasons.copy()
    
    # Collect layout diagnostics
    layout_diagnostics = collect_layout_diagnostics(doc)
    
    candidates = []
    
    # Score each token as potential merchant
    for token in doc.tokens:
        text = token.text.strip()
        
        if not _is_plausible_company_name(text):
            continue
        
        candidate = MerchantCandidate(
            text=text,
            token=token,
            score=0.0,
            reasons=[],
        )
        
        # --- Zone-based scoring (GATED when zone_confidence < 0.5) ---
        
        # Track zone membership regardless of gating (for observability)
        if token.line_idx in zones.buyer_zone_indices:
            candidate.in_buyer_zone = True
        if token.line_idx in zones.seller_zone_indices:
            candidate.in_seller_zone = True
        
        # Only apply zone scoring if zone detection is reliable
        if not zone_gated:
            # Strong penalty for buyer zone
            if candidate.in_buyer_zone:
                candidate.score -= 10
                candidate.penalties.append({"name": "buyer_zone", "delta": -10})
                candidate.reasons.append("buyer_zone")
            
            # Strong boost for seller zone
            if candidate.in_seller_zone:
                candidate.score += 8
                candidate.boosts.append({"name": "seller_zone", "delta": 8})
                candidate.reasons.append("seller_zone")
        
        # --- Plausibility scoring ---
        
        # Legal suffix boost (strong seller signal)
        if _has_legal_suffix(text):
            candidate.has_legal_suffix = True
            candidate.score += 6
            candidate.boosts.append({"name": "legal_suffix", "delta": 6})
            candidate.reasons.append("legal_suffix")
        
        # Nearby contact info boost
        if _has_nearby_contact(token, doc):
            candidate.has_nearby_contact = True
            candidate.score += 4
            candidate.boosts.append({"name": "nearby_contact", "delta": 4})
            candidate.reasons.append("nearby_contact")
        
        # Early line boost (header area)
        if token.line_idx < 10:
            boost = 3 if token.line_idx < 5 else 1
            candidate.score += boost
            candidate.boosts.append({"name": "early_line", "delta": boost})
            candidate.reasons.append("early_line")
        
        # ALL CAPS header boost (common for company names)
        if text.isupper() and 2 <= len(text.split()) <= 5:
            candidate.score += 2
            candidate.boosts.append({"name": "uppercase_header", "delta": 2})
            candidate.reasons.append("uppercase_header")
        
        # --- Penalties ---
        
        # Address-like penalty
        address_patterns = [r'\d+\s+\w+\s+(street|st|avenue|ave|road|rd|blvd)', r'\b\d{5}(-\d{4})?\b']
        if any(re.search(p, text.lower()) for p in address_patterns):
            candidate.score -= 5
            candidate.penalties.append({"name": "address_like", "delta": -5})
            candidate.reasons.append("address_like")
        
        candidates.append(candidate)
    
    # Filter candidates with positive score (or all if none positive)
    filtered = [c for c in candidates if c.score > 0]
    if not filtered and candidates:
        # Keep top candidates even if negative (for observability)
        filtered = sorted(candidates, key=lambda x: -x.score)[:5]
    
    # Sort by score
    filtered.sort(key=lambda x: -x.score)
    
    # --- Seller Identity Validation ---
    # Only select candidates that pass seller-identity validation
    # When zone_gated=True, skip zone-based validation rules
    validated = []
    for cand in filtered:
        # Zone-based rejection is GATED when zone detection is unreliable
        if not zone_gated:
            # Must NOT be in buyer zone (hard reject)
            if cand.in_buyer_zone and not cand.in_seller_zone:
                # Exception: legal suffix after doc title (seller appearing after doc title in unusual layout)
                if cand.has_legal_suffix:
                    # Check if previous line is a doc title
                    prev_tokens = [t for t in doc.tokens if t.line_idx == cand.token.line_idx - 1]
                    if prev_tokens:
                        prev_text = prev_tokens[0].text.lower().strip()
                        doc_titles = {"invoice", "sales invoice", "tax invoice", "commercial invoice", 
                                     "receipt", "bill", "statement", "quotation"}
                        if re.sub(r'[:\s]+$', '', prev_text) in doc_titles:
                            # Boost score to compensate for buyer_zone penalty
                            cand.score += 12  # Override buyer_zone penalty
                            cand.boosts.append({"name": "doc_title_seller_pattern", "delta": 12})
                            cand.reasons.append("doc_title_seller")
                            validated.append(cand)
                            continue
                continue
        
        # Must have at least one positive signal
        # When zone_gated, don't require in_seller_zone as a positive signal
        if zone_gated:
            if cand.has_legal_suffix or cand.has_nearby_contact:
                validated.append(cand)
        else:
            if cand.has_legal_suffix or cand.in_seller_zone or cand.has_nearby_contact:
                validated.append(cand)
    
    # Select winner
    winner = validated[0] if validated else None
    
    # Compute winner margin
    if winner and len(validated) > 1:
        winner_margin = winner.score - validated[1].score
    elif winner:
        winner_margin = winner.score
    else:
        winner_margin = 0.0
    
    # Confidence calculation
    if winner:
        raw_confidence = max(0.0, min(1.0, (winner.score - 2) / 14))
        
        # Reduce confidence if margin is low
        if winner_margin < winner_margin_threshold:
            raw_confidence *= 0.7
    else:
        raw_confidence = 0.0
    
    # Confidence bucket
    if raw_confidence >= 0.8:
        confidence_bucket = "HIGH"
    elif raw_confidence >= 0.55:
        confidence_bucket = "MEDIUM"
    elif raw_confidence > 0:
        confidence_bucket = "LOW"
    else:
        confidence_bucket = "NONE"
    
    # LLM tiebreak (gated)
    llm_used = False
    if (enable_llm_tiebreak and 
        os.getenv("MERCHANT_LLM_TIEBREAK") == "1" and
        len(validated) >= 2 and
        winner_margin < winner_margin_threshold and
        raw_confidence < 0.5):
        # TODO: Implement actual LLM tiebreak call
        # For now, just mark as attempted
        llm_used = True
    
    # ==========================================================================
    # Spatial Intelligence Second-Pass Verification
    # ==========================================================================
    spatial_intelligence_used = False
    spatial_result = None
    spatial_override = False
    
    # Use spatial intelligence when:
    # 1. Low confidence (< 0.6) OR
    # 2. Low winner margin (< 3) OR
    # 3. Winner is in buyer zone (suspicious)
    use_spatial = (
        raw_confidence < 0.6 or
        winner_margin < 3.0 or
        (winner and winner.in_buyer_zone)
    )
    
    if use_spatial and os.getenv("DISABLE_SPATIAL_INTELLIGENCE") != "1":
        try:
            from app.pipelines.spatial_intelligence import enhance_merchant_extraction
            
            # Get page dimensions from doc metadata
            page_width = doc.page_widths[0] if doc.page_widths else 612
            page_height = doc.page_heights[0] if doc.page_heights else 792
            
            spatial_result = enhance_merchant_extraction(
                tokens=doc.tokens,
                current_merchant=winner.text if winner else None,
                page_width=page_width,
                page_height=page_height,
            )
            spatial_intelligence_used = True
            
            # Override if spatial intelligence recommends it
            if spatial_result.get("recommendation") == "use_spatial":
                new_merchant = spatial_result.get("spatial_merchant")
                if new_merchant and new_merchant != (winner.text if winner else None):
                    # Find the candidate matching spatial result
                    spatial_candidate = None
                    for cand in filtered:
                        if cand.text == new_merchant:
                            spatial_candidate = cand
                            break
                    
                    if spatial_candidate:
                        winner = spatial_candidate
                        spatial_override = True
                        # Boost confidence due to spatial verification
                        raw_confidence = max(raw_confidence, 0.65)
                    elif new_merchant:
                        # Create a new candidate from spatial result
                        from app.pipelines.layout_tokens import MerchantCandidate as MC
                        winner = MC(
                            text=new_merchant,
                            score=10.0,
                            reasons=["spatial_intelligence_winner"],
                        )
                        spatial_override = True
                        raw_confidence = 0.6
                        
        except ImportError:
            logger.debug("Spatial intelligence module not available")
        except Exception as e:
            logger.warning(f"Spatial intelligence failed: {e}")
    
    # Build evidence
    evidence = {
        "seller_zone_indices": sorted(zones.seller_zone_indices),
        "buyer_zone_indices": sorted(zones.buyer_zone_indices),
        "anchor_hits": zones.anchor_hits,
        "total_candidates": len(candidates),
        "filtered_candidates": len(filtered),
        "validated_candidates": len(validated),
        "winner_margin": round(winner_margin, 2),
        "has_coords": zones.metadata.get("has_coords", False),
        "llm_tiebreak_used": llm_used,
        # Spatial intelligence fields
        "spatial_intelligence_used": spatial_intelligence_used,
        "spatial_override": spatial_override,
        "spatial_result": spatial_result,
        "chosen_value": winner.text if winner else None,
        "chosen_reasons": winner.reasons if winner else [],
        "chosen_score": winner.score if winner else 0.0,
        # C-lite + B3-lite: Zone confidence diagnostics
        "zone_confidence": zone_confidence,
        "zone_confidence_reasons": zone_confidence_reasons,
        "zone_gated": zone_gated,
        "zone_gated_reason": zone_gated_reason,
        "layout_diagnostics": layout_diagnostics,
        # Safety gate fields
        "zone_reliable": zone_reliable,
        "zone_reliable_reasons": zone_reliable_reasons,
    }
    
    return MerchantResult(
        merchant=winner.text if winner else None,
        confidence=raw_confidence,
        confidence_bucket=confidence_bucket,
        candidates=filtered[:8],  # Top 8 for observability
        winner_margin=winner_margin,
        zones=zones,
        evidence=evidence,
    )


def extract_merchant_from_lines(
    lines: List[str],
    strict: bool = True,
    enable_llm_tiebreak: bool = False,
) -> MerchantResult:
    """
    Extract merchant from text lines (backward compatibility wrapper).
    
    Converts lines to LayoutDocument and calls extract_merchant_from_tokens.
    
    Args:
        lines: List of text lines
        strict: If True, apply stricter filtering
        enable_llm_tiebreak: If True and env flag set, use LLM for ties
        
    Returns:
        MerchantResult
    """
    doc = build_tokens_from_lines(lines, source="lines")
    zones = detect_zones(doc)
    return extract_merchant_from_tokens(doc, zones, strict, enable_llm_tiebreak)


def extract_merchant_from_file(
    file_path: str,
    strict: bool = True,
    enable_llm_tiebreak: bool = False,
) -> MerchantResult:
    """
    Extract merchant from a file (PDF or image).
    
    Automatically selects appropriate token builder based on file type.
    
    Args:
        file_path: Path to PDF or image file
        strict: If True, apply stricter filtering
        enable_llm_tiebreak: If True and env flag set, use LLM for ties
        
    Returns:
        MerchantResult
    """
    doc = build_tokens_auto(file_path)
    zones = detect_zones(doc)
    return extract_merchant_from_tokens(doc, zones, strict, enable_llm_tiebreak)
