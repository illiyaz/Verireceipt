"""
PDF extraction for warranty claims.

Supports dual-mode image extraction:
- Mode A: Embedded images (fast, direct extraction)
- Mode B: Render page and crop image regions (reliable fallback)
"""

import io
import re
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image
    import PIL.ExifTags as ExifTags
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("⚠️ OpenCV not available - advanced image detection disabled")


@dataclass
class ExtractedImage:
    """Image extracted from PDF."""
    data: bytes
    page: int
    index: int
    method: str  # "embedded" or "render_crop"
    bbox: Optional[Tuple[int, int, int, int]] = None
    width: int = 0
    height: int = 0
    size: int = 0  # Size in bytes - used to filter template images
    phash: Optional[str] = None
    dhash: Optional[str] = None
    file_hash: Optional[str] = None
    exif: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedClaim:
    """Structured data extracted from warranty claim PDF."""
    claim_id: Optional[str] = None
    customer_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    vin: Optional[str] = None
    odometer: Optional[int] = None
    issue_description: Optional[str] = None
    claim_date: Optional[str] = None
    decision_date: Optional[str] = None
    parts_cost: Optional[float] = None
    labor_cost: Optional[float] = None
    tax: Optional[float] = None
    total_amount: Optional[float] = None
    status: Optional[str] = None
    rejection_reason: Optional[str] = None
    raw_text: str = ""
    images: List[ExtractedImage] = field(default_factory=list)


class WarrantyClaimExtractor:
    """
    Extract structured data and images from warranty claim PDFs.
    """
    
    # Patterns for field extraction
    PATTERNS = {
        "claim_id": r"Claim\s*ID[:\s]*([A-Z0-9]{6,})",
        "customer_name": r"Customer\s*Name[:\s]*([A-Za-z\s]+?)(?:\n|Vehicle|$)",
        "brand": r"(?:Brand|Make|Manufacturer)[:\s]*([A-Za-z]+)",
        "vehicle_model": r"Vehicle\s*Model[:\s]*([A-Za-z0-9\s\-]+?)(?:\n|Year|$)",
        "year": r"Year[:\s]*(\d{4})",
        "vin": r"VIN[:\s]*([A-HJ-NPR-Z0-9]{17})",
        "odometer": r"(?:Odometer|Mileage)[:\s]*([\d,]+)",
        "issue_description": r"Issue\s*Description[:\s]*([^\n]+)",
        "claim_date": r"Claim\s*Date[:\s]*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
        "decision_date": r"(?:Status\s*Change\s*Date|Decision\s*Date|Approval\s*Date|Rejection\s*Date)[:\s]*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
        "parts_cost": r"Parts?\s*Cost[:\s]*\$?([\d,]+\.?\d*)",
        "labor_cost": r"Labor\s*Cost[:\s]*\$?([\d,]+\.?\d*)",
        "tax": r"Tax(?:es)?[:\s]*\$?([\d,\-]+\.?\d*)",
        "total_amount": r"(?:Claim\s*Amount|Total)[^:\n]*[:\s]*\$?([\d,]+\.?\d*)",
        "status": r"Claim\s*Status[:\s]*(Pending|Approved|Rejected)",
        "rejection_reason": r"(?:Reason\s*(?:for\s*)?(?:Rejection)?|Reason)[:\s]*([^\n]+?)(?:\n\n|Material|$)",
    }
    
    # Known auto brands for extraction
    AUTO_BRANDS = {
        "Honda", "Toyota", "Chevrolet", "Ford", "Subaru", "Mazda", 
        "Nissan", "Hyundai", "Kia", "BMW", "Mercedes", "Audi",
        "Volkswagen", "Jeep", "Dodge", "Ram", "GMC", "Buick",
        "Cadillac", "Lexus", "Acura", "Infiniti", "Lincoln"
    }
    
    def __init__(self, render_dpi: int = 150):
        """
        Initialize extractor.
        
        Args:
            render_dpi: DPI for page rendering in Mode B extraction
        """
        self.render_dpi = render_dpi
        
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF (fitz) is required. Install with: pip install pymupdf")
    
    def extract(self, pdf_path: str) -> ExtractedClaim:
        """
        Extract all data from a warranty claim PDF.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            ExtractedClaim with structured data and images
        """
        doc = fitz.open(pdf_path)
        
        # Extract text
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        
        # Parse structured fields
        claim = self._parse_fields(full_text)
        claim.raw_text = full_text
        
        # Extract brand from vehicle model if not found
        if not claim.brand and claim.model:
            claim.brand = self._extract_brand_from_model(claim.model)
        
        # Extract images (dual-mode)
        claim.images = self._extract_images(doc)
        
        doc.close()
        
        return claim
    
    def _parse_fields(self, text: str) -> ExtractedClaim:
        """Parse structured fields from text."""
        claim = ExtractedClaim()
        
        for field_name, pattern in self.PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                
                # Clean and convert values
                if field_name in ("year",):
                    try:
                        setattr(claim, field_name, int(value))
                    except ValueError:
                        pass
                elif field_name in ("parts_cost", "labor_cost", "tax", "total_amount"):
                    try:
                        # Remove commas and handle negative
                        clean_val = value.replace(",", "").replace("$", "")
                        setattr(claim, field_name, float(clean_val))
                    except ValueError:
                        pass
                elif field_name == "odometer":
                    try:
                        setattr(claim, field_name, int(value.replace(",", "")))
                    except ValueError:
                        pass
                elif field_name == "vehicle_model":
                    # Store as model, extract brand separately
                    claim.model = value
                else:
                    setattr(claim, field_name, value)
        
        return claim
    
    def _extract_brand_from_model(self, model_text: str) -> Optional[str]:
        """Extract brand name from vehicle model text."""
        model_upper = model_text.upper()
        for brand in self.AUTO_BRANDS:
            if brand.upper() in model_upper:
                return brand
        return None
    
    def _extract_images(self, doc: fitz.Document) -> List[ExtractedImage]:
        """
        Extract images using hybrid per-page approach (Variant C).
        
        For each page, intelligently decides:
        - Variant A: Use embedded images if available and sufficient
        - Variant B: For scanned/flattened pages, use text-gap + contour detection
        - Hybrid: Combine methods based on page characteristics
        """
        all_images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_images = self._extract_images_from_page(doc, page, page_num)
            all_images.extend(page_images)
        
        return all_images
    
    def _extract_images_from_page(
        self, 
        doc: fitz.Document, 
        page: fitz.Page, 
        page_num: int
    ) -> List[ExtractedImage]:
        """
        Per-page intelligent image extraction.
        
        Decision logic:
        1. If get_images returns embedded images → use them (Variant A)
        2. If page is image-heavy (low text density) → treat as scan, crop regions
        3. Otherwise → use text-gap + contour detection (Variant B)
        """
        images = []
        
        # Try embedded images first (Variant A)
        embedded = self._extract_embedded_from_page(doc, page, page_num)
        
        # Calculate page characteristics
        text_density = self._calculate_text_density(page)
        has_image_blocks = len(self._detect_image_blocks(page)) > 0
        
        # Decision logic
        if len(embedded) >= 2:
            # Enough embedded images - use them
            return embedded
        elif text_density < 0.1:
            # Very low text density - likely a full-page scan
            # Treat entire page as image (skip, or crop evidence area)
            scan_images = self._extract_from_scan_page(page, page_num)
            return embedded + scan_images
        elif has_image_blocks:
            # Has structural image blocks - extract them
            block_images = self._extract_from_image_blocks(page, page_num)
            return embedded + block_images
        else:
            # Mixed layout - use text-gap + contour detection (Variant B)
            detected_images = self._extract_via_text_gap_and_contours(page, page_num)
            return embedded + detected_images
    
    def _extract_embedded_from_page(
        self, 
        doc: fitz.Document, 
        page: fitz.Page, 
        page_num: int
    ) -> List[ExtractedImage]:
        """Extract embedded image objects from a single page."""
        images = []
        image_list = page.get_images(full=True)
        
        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if base_image:
                    image_data = base_image["image"]
                    extracted = ExtractedImage(
                        data=image_data,
                        page=page_num,
                        index=img_index,
                        method="embedded",
                        width=base_image.get("width", 0),
                        height=base_image.get("height", 0),
                        size=len(image_data)
                    )
                    self._add_image_metadata(extracted)
                    images.append(extracted)
            except Exception as e:
                print(f"Warning: Could not extract image {xref}: {e}")
        
        return images
    
    def _calculate_text_density(self, page: fitz.Page) -> float:
        """
        Calculate text density of a page.
        Returns ratio of text area to page area (0.0 to 1.0).
        Low density (<0.1) suggests scanned page with little/no text layer.
        """
        try:
            text_dict = page.get_text("dict")
            page_area = page.rect.width * page.rect.height
            
            if page_area == 0:
                return 0.0
            
            text_area = 0
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    bbox = block.get("bbox", (0, 0, 0, 0))
                    text_area += (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            
            return text_area / page_area
        except:
            return 0.5  # Default to mixed if error
    
    def _extract_from_scan_page(
        self, 
        page: fitz.Page, 
        page_num: int
    ) -> List[ExtractedImage]:
        """
        Extract from a full-page scan.
        For warranty forms, typically extract bottom portion where evidence photos are.
        """
        images = []
        
        mat = fitz.Matrix(self.render_dpi / 72, self.render_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        
        if not PIL_AVAILABLE:
            return images
        
        page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Crop bottom 40% where evidence photos typically are
        crop_start = int(pix.height * 0.6)
        if crop_start < pix.height - 100:
            cropped = page_img.crop((0, crop_start, pix.width, pix.height))
            
            if self._has_image_content(cropped):
                buf = io.BytesIO()
                cropped.save(buf, format="PNG")
                image_data = buf.getvalue()
                
                extracted = ExtractedImage(
                    data=image_data,
                    page=page_num,
                    index=0,
                    method="scan_crop_bottom",
                    bbox=(0, crop_start, pix.width, pix.height),
                    width=pix.width,
                    height=pix.height - crop_start,
                    size=len(image_data)
                )
                self._add_image_metadata(extracted)
                images.append(extracted)
        
        return images
    
    def _extract_from_image_blocks(
        self, 
        page: fitz.Page, 
        page_num: int
    ) -> List[ExtractedImage]:
        """Extract images from detected structural image blocks."""
        images = []
        image_blocks = self._detect_image_blocks(page)
        
        if not image_blocks or not PIL_AVAILABLE:
            return images
        
        mat = fitz.Matrix(self.render_dpi / 72, self.render_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        scale = self.render_dpi / 72
        
        for block_idx, block in enumerate(image_blocks):
            x0 = int(block[0] * scale)
            y0 = int(block[1] * scale)
            x1 = int(block[2] * scale)
            y1 = int(block[3] * scale)
            
            # Ensure valid crop
            x0 = max(0, min(x0, pix.width - 1))
            y0 = max(0, min(y0, pix.height - 1))
            x1 = max(x0 + 1, min(x1, pix.width))
            y1 = max(y0 + 1, min(y1, pix.height))
            
            if x1 - x0 > 50 and y1 - y0 > 50:
                cropped = page_img.crop((x0, y0, x1, y1))
                
                if self._has_image_content(cropped):
                    buf = io.BytesIO()
                    cropped.save(buf, format="PNG")
                    image_data = buf.getvalue()
                    
                    extracted = ExtractedImage(
                        data=image_data,
                        page=page_num,
                        index=block_idx,
                        method="image_block",
                        bbox=(x0, y0, x1, y1),
                        width=x1 - x0,
                        height=y1 - y0,
                        size=len(image_data)
                    )
                    self._add_image_metadata(extracted)
                    images.append(extracted)
        
        return images
    
    def _extract_via_text_gap_and_contours(
        self, 
        page: fitz.Page, 
        page_num: int
    ) -> List[ExtractedImage]:
        """
        Variant B: Extract images from flattened/scanned PDFs using:
        1. Text-gap detection: mask text blocks, find remaining large rectangles
        2. Contour detection: OpenCV edges + contours for rectangular regions
        """
        images = []
        
        if not PIL_AVAILABLE:
            return images
        
        # Render page
        mat = fitz.Matrix(self.render_dpi / 72, self.render_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        scale = self.render_dpi / 72
        
        # Method 1: Text-gap detection
        text_gap_regions = self._detect_text_gaps(page, pix.width, pix.height, scale)
        
        # Method 2: Contour detection (if OpenCV available)
        contour_regions = []
        if OPENCV_AVAILABLE:
            contour_regions = self._detect_contours(page_img)
        
        # Merge and deduplicate regions
        all_regions = self._merge_regions(text_gap_regions + contour_regions)
        
        for idx, region in enumerate(all_regions):
            x0, y0, x1, y1 = region
            
            if x1 - x0 > 80 and y1 - y0 > 80:  # Min size for evidence photos
                cropped = page_img.crop((x0, y0, x1, y1))
                
                if self._has_image_content(cropped, threshold=0.90):
                    buf = io.BytesIO()
                    cropped.save(buf, format="PNG")
                    image_data = buf.getvalue()
                    
                    extracted = ExtractedImage(
                        data=image_data,
                        page=page_num,
                        index=idx,
                        method="text_gap_contour",
                        bbox=region,
                        width=x1 - x0,
                        height=y1 - y0,
                        size=len(image_data)
                    )
                    self._add_image_metadata(extracted)
                    images.append(extracted)
        
        return images
    
    def _detect_text_gaps(
        self, 
        page: fitz.Page, 
        img_width: int, 
        img_height: int, 
        scale: float
    ) -> List[Tuple[int, int, int, int]]:
        """
        Text-gap detection: find large rectangular areas not covered by text.
        """
        regions = []
        
        try:
            # Get text blocks
            text_dict = page.get_text("dict")
            text_bboxes = []
            
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    bbox = block.get("bbox")
                    if bbox:
                        # Scale to render dimensions
                        text_bboxes.append((
                            int(bbox[0] * scale),
                            int(bbox[1] * scale),
                            int(bbox[2] * scale),
                            int(bbox[3] * scale)
                        ))
            
            if not text_bboxes:
                return regions
            
            # Create mask of text regions
            if OPENCV_AVAILABLE:
                mask = np.ones((img_height, img_width), dtype=np.uint8) * 255
                
                for bbox in text_bboxes:
                    x0, y0, x1, y1 = bbox
                    x0, y0 = max(0, x0), max(0, y0)
                    x1, y1 = min(img_width, x1), min(img_height, y1)
                    mask[y0:y1, x0:x1] = 0
                
                # Find contours in the non-text mask
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for contour in contours:
                    x, y, w, h = cv2.boundingRect(contour)
                    area = w * h
                    
                    # Filter for reasonably sized regions (likely images)
                    if area > 10000 and w > 80 and h > 80:  # Min 100x100 px
                        regions.append((x, y, x + w, y + h))
            else:
                # Fallback: simple grid-based gap detection
                # Divide page into grid and find cells without text
                pass
                
        except Exception as e:
            print(f"Warning: Text-gap detection failed: {e}")
        
        return regions
    
    def _detect_contours(
        self, 
        page_img: Image.Image
    ) -> List[Tuple[int, int, int, int]]:
        """
        Contour detection using OpenCV to find rectangular image regions.
        """
        regions = []
        
        if not OPENCV_AVAILABLE:
            return regions
        
        try:
            # Convert PIL to OpenCV format
            img_array = np.array(page_img)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Edge detection
            edges = cv2.Canny(gray, 50, 150)
            
            # Dilate to connect nearby edges
            kernel = np.ones((5, 5), np.uint8)
            dilated = cv2.dilate(edges, kernel, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                # Approximate contour to polygon
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Look for roughly rectangular shapes (4 corners)
                if len(approx) >= 4:
                    x, y, w, h = cv2.boundingRect(contour)
                    area = w * h
                    
                    # Filter: reasonable size, roughly rectangular aspect ratio
                    aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 999
                    
                    if area > 15000 and w > 100 and h > 100 and aspect_ratio < 4:
                        regions.append((x, y, x + w, y + h))
                        
        except Exception as e:
            print(f"Warning: Contour detection failed: {e}")
        
        return regions
    
    def _merge_regions(
        self, 
        regions: List[Tuple[int, int, int, int]]
    ) -> List[Tuple[int, int, int, int]]:
        """
        Merge overlapping regions and remove duplicates.
        """
        if not regions:
            return []
        
        # Sort by area (largest first)
        regions = sorted(regions, key=lambda r: (r[2]-r[0]) * (r[3]-r[1]), reverse=True)
        
        merged = []
        for region in regions:
            # Check if this region significantly overlaps with existing
            is_duplicate = False
            for existing in merged:
                overlap = self._calculate_overlap(region, existing)
                if overlap > 0.7:  # 70% overlap threshold
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                merged.append(region)
        
        return merged[:10]  # Limit to 10 regions max
    
    def _calculate_overlap(
        self, 
        r1: Tuple[int, int, int, int], 
        r2: Tuple[int, int, int, int]
    ) -> float:
        """Calculate IoU (Intersection over Union) between two rectangles."""
        x1 = max(r1[0], r2[0])
        y1 = max(r1[1], r2[1])
        x2 = min(r1[2], r2[2])
        y2 = min(r1[3], r2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (r1[2] - r1[0]) * (r1[3] - r1[1])
        area2 = (r2[2] - r2[0]) * (r2[3] - r2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def _extract_embedded_images(self, doc: fitz.Document) -> List[ExtractedImage]:
        """Extract images embedded as objects in PDF."""
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                
                try:
                    base_image = doc.extract_image(xref)
                    if base_image:
                        image_data = base_image["image"]
                        
                        # Calculate hashes
                        extracted = ExtractedImage(
                            data=image_data,
                            page=page_num,
                            index=img_index,
                            method="embedded",
                            width=base_image.get("width", 0),
                            height=base_image.get("height", 0),
                            size=len(image_data)  # Size in bytes for template filtering
                        )
                        
                        # Add hashes and EXIF
                        self._add_image_metadata(extracted)
                        images.append(extracted)
                        
                except Exception as e:
                    print(f"Warning: Could not extract image {xref}: {e}")
                    continue
        
        return images
    
    def _extract_rendered_images(self, doc: fitz.Document) -> List[ExtractedImage]:
        """
        Render pages and extract image regions.
        
        Uses multiple strategies:
        1. Detect image blocks from page structure
        2. Fall back to bottom-half crop for standard forms
        """
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get page dimensions
            rect = page.rect
            page_width = rect.width
            page_height = rect.height
            
            # Strategy 1: Find image blocks using page structure
            image_blocks = self._detect_image_blocks(page)
            
            if image_blocks:
                # Render page at high DPI
                mat = fitz.Matrix(self.render_dpi / 72, self.render_dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                scale = self.render_dpi / 72
                
                for block_idx, block in enumerate(image_blocks):
                    # Scale bbox to rendered dimensions
                    x0 = int(block[0] * scale)
                    y0 = int(block[1] * scale)
                    x1 = int(block[2] * scale)
                    y1 = int(block[3] * scale)
                    
                    # Ensure valid crop region
                    x0 = max(0, min(x0, pix.width - 1))
                    y0 = max(0, min(y0, pix.height - 1))
                    x1 = max(x0 + 1, min(x1, pix.width))
                    y1 = max(y0 + 1, min(y1, pix.height))
                    
                    if x1 - x0 > 50 and y1 - y0 > 50:  # Min size threshold
                        cropped = page_img.crop((x0, y0, x1, y1))
                        
                        # Convert to bytes
                        buf = io.BytesIO()
                        cropped.save(buf, format="PNG")
                        image_data = buf.getvalue()
                        
                        extracted = ExtractedImage(
                            data=image_data,
                            page=page_num,
                            index=block_idx,
                            method="render_crop",
                            bbox=(x0, y0, x1, y1),
                            width=x1 - x0,
                            height=y1 - y0,
                            size=len(image_data)
                        )
                        
                        self._add_image_metadata(extracted)
                        images.append(extracted)
            
            else:
                # Strategy 2: Crop bottom portion (common for warranty forms with images at bottom)
                mat = fitz.Matrix(self.render_dpi / 72, self.render_dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Crop bottom 40%
                crop_start = int(pix.height * 0.6)
                if crop_start < pix.height - 100:  # Ensure meaningful crop
                    cropped = page_img.crop((0, crop_start, pix.width, pix.height))
                    
                    # Check if region has significant content (not just white)
                    if self._has_image_content(cropped):
                        buf = io.BytesIO()
                        cropped.save(buf, format="PNG")
                        image_data = buf.getvalue()
                        
                        extracted = ExtractedImage(
                            data=image_data,
                            page=page_num,
                            index=0,
                            method="render_crop_bottom",
                            bbox=(0, crop_start, pix.width, pix.height),
                            width=pix.width,
                            height=pix.height - crop_start,
                            size=len(image_data)
                        )
                        
                        self._add_image_metadata(extracted)
                        images.append(extracted)
        
        return images
    
    def _detect_image_blocks(self, page: fitz.Page) -> List[Tuple[float, float, float, float]]:
        """Detect image regions using page structure analysis."""
        blocks = page.get_text("dict")["blocks"]
        image_blocks = []
        
        for block in blocks:
            # Type 1 = image block
            if block.get("type") == 1:
                bbox = block.get("bbox")
                if bbox:
                    image_blocks.append(bbox)
        
        return image_blocks
    
    def _has_image_content(self, img: Image.Image, threshold: float = 0.95) -> bool:
        """Check if image region has meaningful content (not just white/blank)."""
        if not PIL_AVAILABLE:
            return True
        
        # Convert to grayscale and check variance
        gray = img.convert("L")
        pixels = list(gray.getdata())
        
        # Count near-white pixels
        white_count = sum(1 for p in pixels if p > 250)
        white_ratio = white_count / len(pixels)
        
        return white_ratio < threshold
    
    def _add_image_metadata(self, extracted: ExtractedImage):
        """Add hashes and EXIF metadata to extracted image."""
        # File hash (MD5)
        extracted.file_hash = hashlib.md5(extracted.data).hexdigest()
        
        if not PIL_AVAILABLE:
            return
        
        try:
            img = Image.open(io.BytesIO(extracted.data))
            extracted.width = img.width
            extracted.height = img.height
            
            # Perceptual and difference hashes
            if IMAGEHASH_AVAILABLE:
                extracted.phash = str(imagehash.phash(img))
                extracted.dhash = str(imagehash.dhash(img))
            
            # EXIF extraction
            exif_data = {}
            if hasattr(img, "_getexif") and img._getexif():
                exif = img._getexif()
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    
                    if tag == "DateTimeOriginal":
                        exif_data["timestamp"] = str(value)
                    elif tag == "GPSInfo":
                        exif_data["gps_raw"] = str(value)
                        # Parse GPS coordinates if available
                        gps = self._parse_gps(value)
                        if gps:
                            exif_data["gps_lat"] = gps[0]
                            exif_data["gps_lon"] = gps[1]
                    elif tag == "Make":
                        exif_data["device"] = str(value)
                    elif tag == "Model":
                        exif_data["device_model"] = str(value)
                    elif tag == "Software":
                        exif_data["software"] = str(value)
            
            extracted.exif = exif_data
            
        except Exception as e:
            print(f"Warning: Could not process image metadata: {e}")
    
    def _parse_gps(self, gps_info: Dict) -> Optional[Tuple[float, float]]:
        """Parse GPS coordinates from EXIF GPSInfo."""
        try:
            def convert_to_degrees(value):
                d, m, s = value
                return d + (m / 60.0) + (s / 3600.0)
            
            lat = convert_to_degrees(gps_info.get(2, (0, 0, 0)))
            lon = convert_to_degrees(gps_info.get(4, (0, 0, 0)))
            
            if gps_info.get(1) == "S":
                lat = -lat
            if gps_info.get(3) == "W":
                lon = -lon
            
            return (lat, lon)
        except:
            return None


def extract_warranty_claim(pdf_path: str) -> ExtractedClaim:
    """Convenience function to extract a warranty claim."""
    extractor = WarrantyClaimExtractor()
    return extractor.extract(pdf_path)
