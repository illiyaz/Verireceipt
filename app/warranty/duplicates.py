"""
Duplicate detection for warranty claims.

Detects:
1. Exact image duplicates (file hash match)
2. Similar images (perceptual hash within threshold)
3. Claim duplicates (same VIN + similar issue + close dates)
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

# Configure logging for duplicate detection
logger = logging.getLogger("warranty.duplicates")
logger.setLevel(logging.DEBUG)

# Add console handler if not already present
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(handler)

from .db import (
    find_similar_images,
    find_exact_image,
    save_duplicate_match,
    get_connection,
    get_hash_claim_count,
    get_phash_claim_count
)


@dataclass
class DuplicateMatch:
    """A detected duplicate."""
    matched_claim_id: str
    match_type: str  # IMAGE_EXACT, IMAGE_SIMILAR, VIN_ISSUE_DUPLICATE
    similarity_score: float
    image_index_current: Optional[int] = None
    image_index_matched: Optional[int] = None
    details: str = ""


class DuplicateDetector:
    """
    Detect duplicate images and claims.
    
    Uses dynamic template detection instead of hardcoded hashes:
    1. Aspect ratio check - banners/headers have extreme ratios (>5:1 or <1:5)
    2. Dimension check - very short/narrow images are likely decorative
    3. Frequency check - images appearing in many claims are templates
    """
    
    # Thresholds for duplicate detection
    IMAGE_SIMILAR_THRESHOLD = 10  # Hamming distance for "similar"
    IMAGE_LIKELY_SAME_THRESHOLD = 5  # Hamming distance for "likely same"
    CLAIM_DATE_WINDOW_DAYS = 90  # Days to check for similar claims
    
    # Dynamic template detection thresholds
    MIN_IMAGE_SIZE_BYTES = 5_000  # 5KB minimum (very small = icon/logo)
    MAX_ASPECT_RATIO = 5.0  # Width/height ratio > 5 = banner/header
    MIN_ASPECT_RATIO = 0.2  # Width/height ratio < 0.2 = vertical banner
    MIN_HEIGHT_PX = 200  # Images shorter than this are likely decorative
    MIN_WIDTH_PX = 200  # Images narrower than this are likely decorative
    TEMPLATE_FREQUENCY_THRESHOLD = 3  # If image appears in 3+ claims, it's a template
    
    def __init__(self):
        pass
    
    def _is_likely_template(self, img: Dict[str, Any]) -> tuple[bool, str]:
        """
        Dynamically detect if an image is likely a template/logo/banner.
        
        Returns:
            (is_template, reason) tuple
        """
        width = img.get("width", 0)
        height = img.get("height", 0)
        size = img.get("size", 0)
        file_hash = img.get("file_hash", "")
        
        # Check 1: Very small file size (icons, logos)
        if size > 0 and size < self.MIN_IMAGE_SIZE_BYTES:
            return True, f"size {size} bytes < {self.MIN_IMAGE_SIZE_BYTES} (likely icon/logo)"
        
        # Check 2: Extreme aspect ratio (banners, headers, footers)
        if width > 0 and height > 0:
            aspect_ratio = width / height
            
            if aspect_ratio > self.MAX_ASPECT_RATIO:
                return True, f"aspect ratio {aspect_ratio:.1f}:1 > {self.MAX_ASPECT_RATIO}:1 (likely banner/header)"
            
            if aspect_ratio < self.MIN_ASPECT_RATIO:
                return True, f"aspect ratio 1:{1/aspect_ratio:.1f} (likely vertical banner)"
        
        # Check 3: Very short or narrow dimensions
        if 0 < height < self.MIN_HEIGHT_PX and width > height * 3:
            return True, f"height {height}px < {self.MIN_HEIGHT_PX}px with wide aspect (likely header)"
        
        if 0 < width < self.MIN_WIDTH_PX and height > width * 3:
            return True, f"width {width}px < {self.MIN_WIDTH_PX}px with tall aspect (likely sidebar)"
        
        # Check 4: Frequency-based detection (appears in many claims = template)
        if file_hash:
            claim_count = get_hash_claim_count(file_hash)
            if claim_count >= self.TEMPLATE_FREQUENCY_THRESHOLD:
                return True, f"appears in {claim_count} claims >= {self.TEMPLATE_FREQUENCY_THRESHOLD} (common template)"
        
        return False, ""
    
    def check_duplicates(
        self,
        claim_id: str,
        images: List[Dict[str, Any]],
        vin: Optional[str] = None,
        issue_description: Optional[str] = None,
        claim_date: Optional[str] = None
    ) -> List[DuplicateMatch]:
        """
        Check for all types of duplicates.
        
        Args:
            claim_id: Current claim ID (to exclude from matches)
            images: List of image dicts with phash, dhash, file_hash
            vin: Vehicle VIN for claim-level duplicate check
            issue_description: Issue description for similarity matching
            claim_date: Claim date for temporal proximity check
            
        Returns:
            List of DuplicateMatch objects
        """
        matches = []
        
        logger.info(f"=" * 60)
        logger.info(f"DUPLICATE CHECK: Claim {claim_id}")
        logger.info(f"  VIN: {vin}")
        logger.info(f"  Issue: {issue_description}")
        logger.info(f"  Date: {claim_date}")
        logger.info(f"  Images to check: {len(images)}")
        
        # Check image duplicates
        for img_idx, img in enumerate(images):
            img_size = img.get("size", 0)
            img_width = img.get("width", 0)
            img_height = img.get("height", 0)
            file_hash = img.get("file_hash", "")[:12] if img.get("file_hash") else "None"
            
            logger.debug(f"  Image {img_idx}: size={img_size}B, dims={img_width}x{img_height}, hash={file_hash}...")
            
            # Dynamic template detection (replaces hardcoded hash list)
            is_template, template_reason = self._is_likely_template(img)
            if is_template:
                logger.info(f"  ⏭️  SKIP Image {img_idx}: {template_reason}")
                continue
            
            img_matches = self._check_image_duplicates(
                claim_id=claim_id,
                image_index=img_idx,
                phash=img.get("phash"),
                file_hash=img.get("file_hash"),
                image_size=img_size
            )
            matches.extend(img_matches)
        
        # Check claim-level duplicates (same VIN, similar issue)
        if vin:
            claim_matches = self._check_claim_duplicates(
                claim_id=claim_id,
                vin=vin,
                issue_description=issue_description,
                claim_date=claim_date
            )
            matches.extend(claim_matches)
        
        return matches
    
    def _check_image_duplicates(
        self,
        claim_id: str,
        image_index: int,
        phash: Optional[str],
        file_hash: Optional[str],
        image_size: int = 0
    ) -> List[DuplicateMatch]:
        """Check for duplicate images."""
        matches = []
        
        logger.debug(f"    Checking image {image_index} for duplicates...")
        logger.debug(f"      file_hash: {file_hash[:16] if file_hash else 'None'}...")
        logger.debug(f"      phash: {phash[:16] if phash else 'None'}...")
        
        # Check exact match first
        if file_hash:
            exact_match = find_exact_image(file_hash, exclude_claim_id=claim_id)
            if exact_match:
                matched_claim = exact_match["claim_id"]
                matched_idx = exact_match.get("image_index")
                
                logger.warning(f"    🔴 EXACT MATCH FOUND!")
                logger.warning(f"       Current: claim={claim_id}, img_idx={image_index}, size={image_size}")
                logger.warning(f"       Matched: claim={matched_claim}, img_idx={matched_idx}")
                logger.warning(f"       Hash: {file_hash}")
                
                matches.append(DuplicateMatch(
                    matched_claim_id=exact_match["claim_id"],
                    match_type="IMAGE_EXACT",
                    similarity_score=1.0,
                    image_index_current=image_index,
                    image_index_matched=exact_match.get("image_index"),
                    details=f"Exact image match (identical file hash: {file_hash[:16]}..., size: {image_size} bytes)"
                ))
                
                # Save to database
                save_duplicate_match(
                    claim_id_1=claim_id,
                    claim_id_2=exact_match["claim_id"],
                    match_type="IMAGE_EXACT",
                    similarity_score=1.0,
                    image_index_1=image_index,
                    image_index_2=exact_match.get("image_index"),
                    details="Exact image match"
                )
        
        # Check perceptual hash similarity
        if phash:
            logger.debug(f"    Checking perceptual hash similarity...")
            similar_matches = find_similar_images(
                phash=phash,
                exclude_claim_id=claim_id,
                max_hamming_distance=self.IMAGE_SIMILAR_THRESHOLD
            )
            
            logger.debug(f"    Found {len(similar_matches)} similar image candidates")
            
            for sim in similar_matches:
                # Skip if already found as exact match
                if any(m.matched_claim_id == sim["claim_id"] and 
                       m.match_type == "IMAGE_EXACT" for m in matches):
                    continue
                
                distance = sim["hamming_distance"]
                
                if distance <= self.IMAGE_LIKELY_SAME_THRESHOLD:
                    match_type = "IMAGE_LIKELY_SAME"
                    details = f"Very similar image (hamming distance: {distance})"
                    logger.warning(f"    🟠 LIKELY SAME IMAGE: claim={sim['claim_id']}, distance={distance}")
                else:
                    match_type = "IMAGE_SIMILAR"
                    details = f"Similar image (hamming distance: {distance})"
                    logger.info(f"    🟡 SIMILAR IMAGE: claim={sim['claim_id']}, distance={distance}")
                
                matches.append(DuplicateMatch(
                    matched_claim_id=sim["claim_id"],
                    match_type=match_type,
                    similarity_score=sim["similarity_score"],
                    image_index_current=image_index,
                    image_index_matched=sim.get("image_index"),
                    details=details
                ))
                
                # Save to database
                save_duplicate_match(
                    claim_id_1=claim_id,
                    claim_id_2=sim["claim_id"],
                    match_type=match_type,
                    similarity_score=sim["similarity_score"],
                    image_index_1=image_index,
                    image_index_2=sim.get("image_index"),
                    details=details
                )
        
        return matches
    
    def _check_claim_duplicates(
        self,
        claim_id: str,
        vin: str,
        issue_description: Optional[str],
        claim_date: Optional[str]
    ) -> List[DuplicateMatch]:
        """
        Check for claim-level duplicates.
        
        Same VIN + similar issue + within date window = potential duplicate.
        """
        matches = []
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Find claims with same VIN
        cursor.execute("""
            SELECT id, issue_description, claim_date, status, dealer_id
            FROM warranty_claims 
            WHERE vin = ? AND id != ?
        """, (vin, claim_id))
        
        vin_matches = cursor.fetchall()
        
        for row in vin_matches:
            matched_id = row["id"]
            matched_issue = row["issue_description"] or ""
            matched_date = row["claim_date"]
            
            # Check issue similarity
            issue_similarity = self._calculate_issue_similarity(
                issue_description or "", matched_issue
            )
            
            # Check date proximity
            date_proximity = self._calculate_date_proximity(
                claim_date, matched_date
            )
            
            # High similarity + recent = likely duplicate
            if issue_similarity > 0.7 and date_proximity > 0.5:
                overall_score = (issue_similarity + date_proximity) / 2
                
                matches.append(DuplicateMatch(
                    matched_claim_id=matched_id,
                    match_type="VIN_ISSUE_DUPLICATE",
                    similarity_score=overall_score,
                    details=f"Same VIN with similar issue (issue sim: {issue_similarity:.2f}, "
                            f"date proximity: {date_proximity:.2f})"
                ))
                
                save_duplicate_match(
                    claim_id_1=claim_id,
                    claim_id_2=matched_id,
                    match_type="VIN_ISSUE_DUPLICATE",
                    similarity_score=overall_score,
                    details=f"Same VIN, issue similarity: {issue_similarity:.2f}"
                )
        
        return matches
    
    def _calculate_issue_similarity(self, issue1: str, issue2: str) -> float:
        """
        Calculate similarity between two issue descriptions.
        Uses word overlap (Jaccard similarity).
        """
        if not issue1 or not issue2:
            return 0.0
        
        # Normalize and tokenize
        words1 = set(issue1.lower().split())
        words2 = set(issue2.lower().split())
        
        # Remove common stopwords
        stopwords = {"the", "a", "an", "is", "was", "be", "to", "of", "and", "or", "for", "in", "on"}
        words1 = words1 - stopwords
        words2 = words2 - stopwords
        
        if not words1 or not words2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_date_proximity(
        self,
        date1: Optional[str],
        date2: Optional[str]
    ) -> float:
        """
        Calculate proximity score between two dates.
        Returns 1.0 if same day, decreasing to 0.0 at CLAIM_DATE_WINDOW_DAYS.
        """
        if not date1 or not date2:
            return 0.5  # Neutral if dates unknown
        
        try:
            # Try parsing different date formats
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    d1 = datetime.strptime(date1, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 0.5
            
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    d2 = datetime.strptime(date2, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 0.5
            
            days_diff = abs((d1 - d2).days)
            
            if days_diff == 0:
                return 1.0
            elif days_diff >= self.CLAIM_DATE_WINDOW_DAYS:
                return 0.0
            else:
                return 1.0 - (days_diff / self.CLAIM_DATE_WINDOW_DAYS)
                
        except Exception:
            return 0.5


def check_for_duplicates(
    claim_id: str,
    images: List[Dict],
    vin: Optional[str] = None,
    issue_description: Optional[str] = None,
    claim_date: Optional[str] = None
) -> List[DuplicateMatch]:
    """Convenience function for duplicate detection."""
    detector = DuplicateDetector()
    return detector.check_duplicates(
        claim_id=claim_id,
        images=images,
        vin=vin,
        issue_description=issue_description,
        claim_date=claim_date
    )
