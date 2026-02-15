#!/usr/bin/env python3
"""
Golden tests for warranty claim duplicate detection.

Tests the dynamic template filtering logic to ensure:
1. Banner/header images are correctly filtered by aspect ratio
2. Small icons/logos are filtered by size
3. Frequent template images are filtered by occurrence count
4. Actual damage photos are NOT filtered (no false negatives)
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.warranty.duplicates import DuplicateDetector


class TestTemplateDetection:
    """Test the _is_likely_template method for dynamic template filtering."""
    
    def setup_method(self):
        """Create detector instance for each test."""
        self.detector = DuplicateDetector()
    
    # =========================================================================
    # Aspect Ratio Tests - Banners/Headers
    # =========================================================================
    
    def test_wide_banner_detected_as_template(self):
        """Wide banner (2480x265) should be detected as template."""
        img = {
            "width": 2480,
            "height": 265,
            "size": 150000,  # 150KB - large enough to pass size check
            "file_hash": "abc123"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is True
        assert "aspect ratio" in reason.lower()
        assert "banner" in reason.lower() or "header" in reason.lower()
    
    def test_header_strip_detected_as_template(self):
        """Header strip (1000x100) should be detected as template."""
        img = {
            "width": 1000,
            "height": 100,
            "size": 50000,
            "file_hash": "def456"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is True
        assert "aspect ratio" in reason.lower() or "height" in reason.lower()
    
    def test_vertical_banner_detected_as_template(self):
        """Vertical banner (100x1000) should be detected as template."""
        img = {
            "width": 100,
            "height": 1000,
            "size": 50000,
            "file_hash": "ghi789"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is True
        assert "aspect ratio" in reason.lower() or "vertical" in reason.lower()
    
    # =========================================================================
    # Size Tests - Icons/Logos
    # =========================================================================
    
    def test_tiny_icon_detected_as_template(self):
        """Tiny icon (<5KB) should be detected as template."""
        img = {
            "width": 32,
            "height": 32,
            "size": 1024,  # 1KB
            "file_hash": "icon123"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is True
        assert "size" in reason.lower()
    
    def test_small_logo_detected_as_template(self):
        """Small logo (4KB) should be detected as template."""
        img = {
            "width": 100,
            "height": 50,
            "size": 4000,  # 4KB
            "file_hash": "logo123"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is True
        assert "size" in reason.lower()
    
    # =========================================================================
    # Valid Photos - Should NOT be filtered
    # =========================================================================
    
    def test_square_damage_photo_not_filtered(self):
        """Square damage photo (800x800) should NOT be filtered."""
        img = {
            "width": 800,
            "height": 800,
            "size": 200000,  # 200KB
            "file_hash": "damage_photo_1"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is False
        assert reason == ""
    
    def test_landscape_photo_not_filtered(self):
        """Landscape photo (1200x900, 4:3) should NOT be filtered."""
        img = {
            "width": 1200,
            "height": 900,
            "size": 350000,  # 350KB
            "file_hash": "landscape_photo"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is False
        assert reason == ""
    
    def test_portrait_photo_not_filtered(self):
        """Portrait photo (900x1200, 3:4) should NOT be filtered."""
        img = {
            "width": 900,
            "height": 1200,
            "size": 350000,
            "file_hash": "portrait_photo"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is False
        assert reason == ""
    
    def test_wide_photo_not_filtered(self):
        """Wide photo (1600x1000, 16:10) should NOT be filtered."""
        img = {
            "width": 1600,
            "height": 1000,
            "size": 500000,
            "file_hash": "wide_photo"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is False
        assert reason == ""
    
    def test_phone_photo_not_filtered(self):
        """Phone camera photo (3000x4000) should NOT be filtered."""
        img = {
            "width": 3000,
            "height": 4000,
            "size": 2000000,  # 2MB
            "file_hash": "phone_photo"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is False
        assert reason == ""
    
    # =========================================================================
    # Edge Cases
    # =========================================================================
    
    def test_missing_dimensions_not_filtered(self):
        """Image with missing dimensions should NOT be filtered by aspect ratio."""
        img = {
            "width": 0,
            "height": 0,
            "size": 100000,
            "file_hash": "unknown_dims"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        # Should not be filtered (can't determine aspect ratio)
        assert is_template is False
    
    def test_missing_size_with_good_aspect_not_filtered(self):
        """Image with missing size but good aspect ratio should NOT be filtered."""
        img = {
            "width": 800,
            "height": 600,
            "size": 0,  # Unknown size
            "file_hash": "unknown_size"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is False
    
    def test_borderline_aspect_ratio_not_filtered(self):
        """Image with aspect ratio exactly at threshold (5:1) should NOT be filtered."""
        img = {
            "width": 1000,
            "height": 200,  # Exactly 5:1
            "size": 100000,
            "file_hash": "borderline"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        # At exactly 5:1, should not trigger (we check > 5.0)
        assert is_template is False
    
    def test_just_over_threshold_filtered(self):
        """Image with aspect ratio just over threshold should be filtered."""
        img = {
            "width": 1001,
            "height": 200,  # 5.005:1 - just over threshold
            "size": 100000,
            "file_hash": "just_over"
        }
        is_template, reason = self.detector._is_likely_template(img)
        
        assert is_template is True


class TestTemplateThresholds:
    """Test that threshold values are sensible."""
    
    def test_aspect_ratio_thresholds(self):
        """Verify aspect ratio thresholds are reasonable."""
        detector = DuplicateDetector()
        
        # MAX should be >= 5 (banners are typically 6:1 or wider)
        assert detector.MAX_ASPECT_RATIO >= 5.0
        
        # MIN should be <= 0.2 (1:5 ratio)
        assert detector.MIN_ASPECT_RATIO <= 0.2
    
    def test_size_threshold(self):
        """Verify size threshold catches icons but not photos."""
        detector = DuplicateDetector()
        
        # Should be small enough to catch icons (< 10KB)
        assert detector.MIN_IMAGE_SIZE_BYTES < 10000
        
        # But not so large that it catches real photos
        assert detector.MIN_IMAGE_SIZE_BYTES < 50000
    
    def test_dimension_thresholds(self):
        """Verify dimension thresholds are reasonable."""
        detector = DuplicateDetector()
        
        # Min height should catch headers but not photos
        assert 100 <= detector.MIN_HEIGHT_PX <= 300
        
        # Min width should catch sidebars but not photos
        assert 100 <= detector.MIN_WIDTH_PX <= 300
    
    def test_frequency_threshold(self):
        """Verify frequency threshold is reasonable."""
        detector = DuplicateDetector()
        
        # Should be at least 2 (need multiple occurrences)
        assert detector.TEMPLATE_FREQUENCY_THRESHOLD >= 2
        
        # Should be small enough to catch common templates
        assert detector.TEMPLATE_FREQUENCY_THRESHOLD <= 5


class TestGoldenCases:
    """
    Golden test cases based on actual warranty claim images.
    These lock in expected behavior for known image dimensions.
    """
    
    def setup_method(self):
        self.detector = DuplicateDetector()
    
    # Known template images from warranty forms
    TEMPLATE_IMAGES = [
        # (width, height, description)
        (2480, 265, "Warranty form header banner"),
        (2341, 218, "Form header with logo"),
        (1876, 1010, "Actually this might be a photo - wide but not extreme"),
        (277, 147, "Small logo image"),
    ]
    
    # Known legitimate damage photos
    LEGITIMATE_PHOTOS = [
        # (width, height, description)
        (1116, 928, "Damage photo - slightly landscape"),
        (916, 958, "Damage photo - nearly square"),
        (1033, 958, "Damage photo - slightly landscape"),
        (813, 877, "Damage photo - nearly square"),
        (952, 701, "Damage photo - landscape"),
        (1005, 701, "Damage photo - landscape"),
    ]
    
    def test_known_banner_filtered(self):
        """The 2480x265 banner should always be filtered."""
        img = {"width": 2480, "height": 265, "size": 100000, "file_hash": "test"}
        is_template, _ = self.detector._is_likely_template(img)
        assert is_template is True, "2480x265 banner should be detected as template"
    
    def test_known_damage_photos_not_filtered(self):
        """Known legitimate damage photos should NOT be filtered."""
        for width, height, desc in self.LEGITIMATE_PHOTOS:
            img = {"width": width, "height": height, "size": 100000, "file_hash": f"test_{width}x{height}"}
            is_template, reason = self.detector._is_likely_template(img)
            assert is_template is False, f"{desc} ({width}x{height}) should NOT be filtered. Got: {reason}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
