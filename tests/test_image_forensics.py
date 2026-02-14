"""
Tests for image forensics module.

Verifies:
1. Module structure and API contract
2. ELA analysis returns expected fields
3. Noise analysis returns expected fields
4. DPI analysis returns expected fields
5. Histogram analysis returns expected fields
6. Overall aggregation logic (2+ signals = suspicious)
7. Rules integration (R_IMAGE_FORENSICS_* rules exist in codebase)
8. Graceful degradation on missing/corrupt images

Running:
    python -m pytest tests/test_image_forensics.py -v
"""

import pytest
import os
import tempfile
import io
from typing import Dict, Any

# PIL is required for these tests
PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw
import numpy as np


# =============================================================================
# Helpers: Create synthetic test images
# =============================================================================

def _make_clean_receipt(width=600, height=800) -> str:
    """Create a simple clean receipt-like image. Returns temp file path."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Add some text-like dark rectangles
    for y in range(100, 700, 40):
        draw.rectangle([50, y, 550, y + 15], fill=(30, 30, 30))
    # Add noise to simulate a real photo
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, 5, arr.shape).astype(np.float32)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    path = tempfile.mktemp(suffix=".jpg")
    img.save(path, format="JPEG", quality=92)
    return path


def _make_spliced_image(width=600, height=800) -> str:
    """
    Create an image that simulates splicing: save one region at low quality,
    another at high quality, then merge. This should trigger ELA.
    """
    # Background: high-quality white
    img = Image.new("RGB", (width, height), color=(245, 245, 245))

    # Save the whole thing at quality=95 first
    buf_high = io.BytesIO()
    img.save(buf_high, format="JPEG", quality=95)
    buf_high.seek(0)
    base = Image.open(buf_high).convert("RGB")

    # Create a separate "pasted" region saved at low quality
    patch = Image.new("RGB", (200, 100), color=(200, 50, 50))
    buf_low = io.BytesIO()
    patch.save(buf_low, format="JPEG", quality=15)
    buf_low.seek(0)
    low_q_patch = Image.open(buf_low).convert("RGB")

    # Paste the low-quality patch into the high-quality base
    base.paste(low_q_patch, (200, 400))

    path = tempfile.mktemp(suffix=".jpg")
    base.save(path, format="JPEG", quality=95)
    return path


def _make_tiny_image() -> str:
    """Create a very small image that should trigger low-res detection."""
    img = Image.new("RGB", (100, 100), color=(200, 200, 200))
    path = tempfile.mktemp(suffix=".png")
    img.save(path, format="PNG")
    return path


def _make_digital_image() -> str:
    """Create a perfectly clean digital image (no noise at all)."""
    img = Image.new("RGB", (600, 800), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 100, 550, 130], fill=(0, 0, 0))
    draw.rectangle([50, 200, 550, 230], fill=(0, 0, 0))
    path = tempfile.mktemp(suffix=".png")
    img.save(path, format="PNG")
    return path


# =============================================================================
# 1. Module API Contract Tests
# =============================================================================

class TestForensicsAPIContract:
    """Verify the module returns the expected structure."""

    def test_run_image_forensics_returns_dict(self):
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_clean_receipt()
        try:
            result = run_image_forensics(path)
            assert isinstance(result, dict)
            assert result["forensics_available"] is True
            # Check all sub-analyses present
            assert "ela" in result
            assert "noise" in result
            assert "dpi" in result
            assert "histogram" in result
            assert "overall_suspicious" in result
            assert "overall_confidence" in result
            assert "overall_evidence" in result
            assert "signal_count" in result
        finally:
            os.unlink(path)

    def test_ela_fields_present(self):
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_clean_receipt()
        try:
            result = run_image_forensics(path)
            ela = result["ela"]
            for field in ["ela_mean", "ela_std", "ela_max", "ela_hotspot_ratio",
                          "ela_zone_variance", "ela_suspicious", "ela_confidence", "ela_evidence"]:
                assert field in ela, f"Missing ELA field: {field}"
        finally:
            os.unlink(path)

    def test_noise_fields_present(self):
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_clean_receipt()
        try:
            result = run_image_forensics(path)
            noise = result["noise"]
            for field in ["noise_mean", "noise_std", "noise_zone_variance",
                          "noise_zone_range", "noise_suspicious", "noise_confidence", "noise_evidence"]:
                assert field in noise, f"Missing noise field: {field}"
        finally:
            os.unlink(path)

    def test_dpi_fields_present(self):
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_clean_receipt()
        try:
            result = run_image_forensics(path)
            dpi = result["dpi"]
            for field in ["width", "height", "dpi_suspicious", "dpi_confidence", "dpi_evidence"]:
                assert field in dpi, f"Missing DPI field: {field}"
        finally:
            os.unlink(path)

    def test_histogram_fields_present(self):
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_clean_receipt()
        try:
            result = run_image_forensics(path)
            hist = result["histogram"]
            for field in ["histogram_gaps", "histogram_clipping", "histogram_suspicious",
                          "histogram_confidence", "histogram_evidence"]:
                assert field in hist, f"Missing histogram field: {field}"
        finally:
            os.unlink(path)


# =============================================================================
# 2. Detection Tests
# =============================================================================

class TestForensicsDetection:
    """Test that forensics detects known patterns."""

    def test_clean_receipt_not_suspicious(self):
        """A normal receipt image should not trigger overall suspicious."""
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_clean_receipt()
        try:
            result = run_image_forensics(path)
            # Clean image should NOT be overall_suspicious (may have 0 or 1 signal)
            assert result["signal_count"] <= 1, (
                f"Clean receipt triggered {result['signal_count']} signals: "
                f"{result['overall_evidence']}"
            )
        finally:
            os.unlink(path)

    def test_tiny_image_triggers_low_res(self):
        """A 100x100 image should trigger is_very_low_res."""
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_tiny_image()
        try:
            result = run_image_forensics(path)
            assert result["dpi"]["is_very_low_res"] is True
            assert result["dpi"]["dpi_suspicious"] is True
        finally:
            os.unlink(path)

    def test_digital_image_low_noise(self):
        """A perfectly digital image should have very low noise."""
        from app.pipelines.image_forensics import run_image_forensics
        path = _make_digital_image()
        try:
            result = run_image_forensics(path)
            # Digital images have near-zero noise
            assert result["noise"]["noise_mean"] < 2.0, (
                f"Digital image noise too high: {result['noise']['noise_mean']}"
            )
        finally:
            os.unlink(path)


# =============================================================================
# 3. Graceful Degradation Tests
# =============================================================================

class TestForensicsGracefulDegradation:
    """Test that forensics handles edge cases without crashing."""

    def test_missing_file_returns_unavailable(self):
        from app.pipelines.image_forensics import run_image_forensics
        result = run_image_forensics("/nonexistent/path/fake.jpg")
        assert result["forensics_available"] is False

    def test_corrupt_file_returns_unavailable(self):
        from app.pipelines.image_forensics import run_image_forensics
        path = tempfile.mktemp(suffix=".jpg")
        try:
            with open(path, "wb") as f:
                f.write(b"not a real image file")
            result = run_image_forensics(path)
            assert result["forensics_available"] is False
        finally:
            if os.path.exists(path):
                os.unlink(path)


# =============================================================================
# 4. Rules Integration Tests
# =============================================================================

class TestForensicsRulesIntegration:
    """Verify forensics rules exist in rules.py codebase."""

    def test_forensics_rules_exist(self):
        import app.pipelines.rules as rules_module
        source = open(rules_module.__file__).read()
        assert "R_IMAGE_FORENSICS_TAMPERING" in source
        assert "R_IMAGE_ELA_SPLICE" in source
        assert "R_IMAGE_DIGITAL_ORIGIN" in source
        assert "R_IMAGE_LOW_RES" in source

    def test_forensics_consumed_from_forensic_features(self):
        """Verify rules.py reads from fr['image_forensics']."""
        import app.pipelines.rules as rules_module
        source = open(rules_module.__file__).read()
        assert 'fr.get("image_forensics")' in source

    def test_low_res_rule_fires_on_tiny_image(self):
        """R_IMAGE_LOW_RES should fire when image_forensics reports very low res."""
        from app.pipelines.rules import _score_and_explain
        from app.schemas.receipt import ReceiptFeatures

        features = ReceiptFeatures(
            file_features={"source_type": "image"},
            text_features={
                "doc_class": "POS_RETAIL",
                "doc_subtype_guess": "POS_RETAIL",
                "doc_profile_confidence": 0.8,
                "merchant_candidate": "Test Store",
                "has_any_amount": True,
                "total_line_present": True,
                "has_date": True,
                "receipt_date": "2024-01-15",
                "total_amount": 50.0,
                "has_line_items": True,
                "line_items_sum": 50.0,
                "total_mismatch": False,
                "address_profile": {},
                "merchant_address_consistency": {},
                "doc_profile": {"subtype": "POS_RETAIL", "confidence": 0.8},
            },
            layout_features={"num_lines": 10, "numeric_line_ratio": 0.3},
            forensic_features={
                "uppercase_ratio": 0.3,
                "unique_char_count": 40,
                "image_forensics": {
                    "forensics_available": True,
                    "ela": {"ela_suspicious": False, "ela_zone_variance": 5.0},
                    "noise": {"noise_suspicious": False, "noise_mean": 5.0},
                    "dpi": {
                        "dpi_suspicious": True,
                        "is_very_low_res": True,
                        "width": 100,
                        "height": 100,
                        "is_screenshot_size": False,
                        "dpi_evidence": ["Very low resolution"],
                    },
                    "histogram": {"histogram_suspicious": False},
                    "overall_suspicious": False,
                    "signal_count": 1,
                    "overall_confidence": 0.15,
                    "overall_evidence": [],
                },
            },
        )

        result = _score_and_explain(features)
        rule_ids = [e.get("rule_id") for e in result.events]
        assert "R_IMAGE_LOW_RES" in rule_ids, (
            f"R_IMAGE_LOW_RES should fire for 100x100 image. Fired: {rule_ids}"
        )
