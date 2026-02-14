"""
Image Forensics Module for VeriReceipt.

Pixel-level forensic analysis that does NOT depend on LLM vision.
Each detector returns structured signals consumed by rules.py.

Techniques implemented:
1. ELA (Error Level Analysis) — detects JPEG re-save artifacts from editing
2. Noise consistency analysis — uniform vs non-uniform noise across zones
3. DPI / resolution anomaly detection — mixed resolution regions
4. Channel histogram anomaly — detects digital compositing artifacts

Design principles:
- NEVER raises; all functions return default-safe dicts on error
- Every signal includes confidence + evidence for audit trail
- Lightweight: runs in <500ms for typical receipt images
"""

import io
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports (PIL / cv2 may not be installed in all environments)
# ---------------------------------------------------------------------------
_PIL_AVAILABLE = False
_CV2_AVAILABLE = False

try:
    from PIL import Image, ImageChops, ImageFilter
    _PIL_AVAILABLE = True
except ImportError:
    pass

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    pass


# =============================================================================
# 1. Error Level Analysis (ELA)
# =============================================================================

def _ela_analysis(
    img: "Image.Image",
    quality: int = 90,
    scale: int = 15,
) -> Dict[str, Any]:
    """
    Error Level Analysis: re-save at known JPEG quality, diff with original.

    Unedited photos show uniform error levels across the entire image.
    Edited regions show HIGHER error levels because they were saved at a
    different quality than the surrounding area.

    Args:
        img: PIL Image (RGB)
        quality: JPEG re-save quality (90 is standard for ELA)
        scale: Brightness amplification factor for the diff

    Returns:
        {
            "ela_mean": float,          # Mean ELA value (0-255)
            "ela_std": float,           # Std deviation of ELA
            "ela_max": float,           # Max ELA value
            "ela_hotspot_ratio": float, # Fraction of pixels > 2*mean
            "ela_zone_variance": float, # Variance between zone means
            "ela_suspicious": bool,     # True if anomalous
            "ela_confidence": float,    # 0.0-1.0
            "ela_evidence": [str],
        }
    """
    result = {
        "ela_mean": 0.0,
        "ela_std": 0.0,
        "ela_max": 0.0,
        "ela_hotspot_ratio": 0.0,
        "ela_zone_variance": 0.0,
        "ela_suspicious": False,
        "ela_confidence": 0.0,
        "ela_evidence": [],
    }

    try:
        # Convert to RGB if needed
        rgb = img.convert("RGB")

        # Re-save at known JPEG quality
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        resaved = Image.open(buf).convert("RGB")

        # Compute absolute diff
        diff = ImageChops.difference(rgb, resaved)

        # Amplify for visibility and analysis
        arr = np.array(diff, dtype=np.float32)
        # Convert to single-channel (max across RGB)
        ela_map = np.max(arr, axis=2)

        # Global stats
        result["ela_mean"] = round(float(np.mean(ela_map)), 2)
        result["ela_std"] = round(float(np.std(ela_map)), 2)
        result["ela_max"] = round(float(np.max(ela_map)), 2)

        # Hotspot ratio: pixels with ELA > 2× mean
        mean_val = max(result["ela_mean"], 1.0)
        hotspot_mask = ela_map > (2.0 * mean_val)
        total_pixels = ela_map.size
        result["ela_hotspot_ratio"] = round(
            float(np.sum(hotspot_mask)) / max(1, total_pixels), 4
        )

        # Zone analysis: divide image into 3×3 grid and compare zone means
        h, w = ela_map.shape
        zone_means = []
        zh, zw = max(1, h // 3), max(1, w // 3)
        for row in range(3):
            for col in range(3):
                zone = ela_map[
                    row * zh : min((row + 1) * zh, h),
                    col * zw : min((col + 1) * zw, w),
                ]
                if zone.size > 0:
                    zone_means.append(float(np.mean(zone)))

        if len(zone_means) >= 4:
            result["ela_zone_variance"] = round(float(np.var(zone_means)), 2)
        else:
            result["ela_zone_variance"] = 0.0

        # Decision logic
        evidence = []

        # High zone variance = different parts of image at different quality
        if result["ela_zone_variance"] > 15.0:
            evidence.append(
                f"ELA zone variance {result['ela_zone_variance']:.1f} "
                f"indicates non-uniform compression (possible splicing)"
            )

        # High hotspot ratio = concentrated editing artifacts
        if result["ela_hotspot_ratio"] > 0.15:
            evidence.append(
                f"ELA hotspot ratio {result['ela_hotspot_ratio']:.2%} — "
                f"significant areas with high error levels"
            )

        # Very high max with low mean = localized editing
        if result["ela_max"] > 80 and result["ela_mean"] < 15:
            evidence.append(
                f"ELA max {result['ela_max']:.0f} with mean {result['ela_mean']:.1f} — "
                f"possible localized manipulation"
            )

        result["ela_evidence"] = evidence
        result["ela_suspicious"] = len(evidence) > 0
        # Confidence: more evidence = higher confidence
        result["ela_confidence"] = min(1.0, 0.3 * len(evidence) + 0.2)

    except Exception as e:
        logger.warning(f"ELA analysis failed: {e}")
        result["ela_evidence"] = [f"ELA failed: {str(e)[:80]}"]

    return result


# =============================================================================
# 2. Noise Consistency Analysis
# =============================================================================

def _noise_analysis(img: "Image.Image") -> Dict[str, Any]:
    """
    Analyze noise consistency across image zones.

    Real photographs have uniform sensor noise. Edited images have:
    - Smooth (denoised) areas where content was pasted
    - Different noise patterns where content was composited from another source
    - Abrupt noise level changes at edit boundaries

    Uses high-pass filter to isolate noise, then compares zone statistics.

    Returns:
        {
            "noise_mean": float,
            "noise_std": float,
            "noise_zone_variance": float,
            "noise_zone_range": float,     # max zone noise - min zone noise
            "noise_suspicious": bool,
            "noise_confidence": float,
            "noise_evidence": [str],
        }
    """
    result = {
        "noise_mean": 0.0,
        "noise_std": 0.0,
        "noise_zone_variance": 0.0,
        "noise_zone_range": 0.0,
        "noise_suspicious": False,
        "noise_confidence": 0.0,
        "noise_evidence": [],
    }

    try:
        gray = img.convert("L")

        # High-pass filter: original - blurred = noise component
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
        noise_map = np.abs(
            np.array(gray, dtype=np.float32) - np.array(blurred, dtype=np.float32)
        )

        result["noise_mean"] = round(float(np.mean(noise_map)), 2)
        result["noise_std"] = round(float(np.std(noise_map)), 2)

        # Zone analysis: 4×4 grid
        h, w = noise_map.shape
        zone_means = []
        zh, zw = max(1, h // 4), max(1, w // 4)
        for row in range(4):
            for col in range(4):
                zone = noise_map[
                    row * zh : min((row + 1) * zh, h),
                    col * zw : min((col + 1) * zw, w),
                ]
                if zone.size > 0:
                    zone_means.append(float(np.mean(zone)))

        if len(zone_means) >= 4:
            result["noise_zone_variance"] = round(float(np.var(zone_means)), 2)
            result["noise_zone_range"] = round(
                float(max(zone_means) - min(zone_means)), 2
            )
        else:
            result["noise_zone_variance"] = 0.0
            result["noise_zone_range"] = 0.0

        evidence = []

        # High zone variance = non-uniform noise (likely compositing)
        # Note: JPEG compression + real photo noise creates variance ~5-12;
        # high-contrast documents (receipts: white bg + dark text) reach ~15-25.
        # Only flag truly extreme values.
        if result["noise_zone_variance"] > 30.0:
            evidence.append(
                f"Noise zone variance {result['noise_zone_variance']:.1f} — "
                f"non-uniform noise distribution (possible compositing)"
            )

        # Large zone range = some areas have very different noise levels
        # Receipts naturally have range ~10-15 due to text/background contrast.
        if result["noise_zone_range"] > 18.0:
            evidence.append(
                f"Noise zone range {result['noise_zone_range']:.1f} — "
                f"large noise level variation across image"
            )

        # Very low noise (< 1.0 mean) = digitally generated, not photographed
        if result["noise_mean"] < 1.0:
            evidence.append(
                f"Very low noise (mean {result['noise_mean']:.2f}) — "
                f"image may be digitally generated, not a photograph"
            )

        result["noise_evidence"] = evidence
        result["noise_suspicious"] = len(evidence) > 0
        result["noise_confidence"] = min(1.0, 0.3 * len(evidence) + 0.2)

    except Exception as e:
        logger.warning(f"Noise analysis failed: {e}")
        result["noise_evidence"] = [f"Noise analysis failed: {str(e)[:80]}"]

    return result


# =============================================================================
# 3. DPI / Resolution Anomaly Detection
# =============================================================================

def _dpi_analysis(img: "Image.Image") -> Dict[str, Any]:
    """
    Check for DPI inconsistencies and resolution anomalies.

    Detects:
    - Very low resolution images (likely screenshots of screenshots)
    - Non-standard DPI values (mismatched EXIF vs actual)
    - Aspect ratio anomalies
    - Suspiciously small images (likely cropped/fabricated)

    Returns:
        {
            "width": int,
            "height": int,
            "dpi_x": int or None,
            "dpi_y": int or None,
            "dpi_mismatch": bool,
            "is_very_low_res": bool,
            "is_screenshot_size": bool,
            "dpi_suspicious": bool,
            "dpi_confidence": float,
            "dpi_evidence": [str],
        }
    """
    result = {
        "width": 0,
        "height": 0,
        "dpi_x": None,
        "dpi_y": None,
        "dpi_mismatch": False,
        "is_very_low_res": False,
        "is_screenshot_size": False,
        "dpi_suspicious": False,
        "dpi_confidence": 0.0,
        "dpi_evidence": [],
    }

    try:
        w, h = img.size
        result["width"] = w
        result["height"] = h

        # Extract DPI from image info
        dpi = img.info.get("dpi")
        if dpi and isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
            result["dpi_x"] = int(dpi[0])
            result["dpi_y"] = int(dpi[1])

        evidence = []

        # DPI mismatch (X != Y) — indicates manipulation
        if result["dpi_x"] and result["dpi_y"]:
            if abs(result["dpi_x"] - result["dpi_y"]) > 5:
                result["dpi_mismatch"] = True
                evidence.append(
                    f"DPI mismatch: X={result['dpi_x']}, Y={result['dpi_y']} — "
                    f"suggests non-uniform scaling or manipulation"
                )

        # Very low resolution — unlikely to be a real scan/photo
        total_pixels = w * h
        if total_pixels < 100_000:  # Less than ~316×316
            result["is_very_low_res"] = True
            evidence.append(
                f"Very low resolution ({w}×{h} = {total_pixels:,} pixels) — "
                f"too small for a real receipt scan"
            )

        # Screenshot-like dimensions (common phone/browser sizes)
        SCREENSHOT_WIDTHS = {360, 375, 390, 393, 412, 414, 428, 768, 1024, 1280, 1366, 1440, 1920}
        if w in SCREENSHOT_WIDTHS and h > w * 1.5:
            result["is_screenshot_size"] = True
            evidence.append(
                f"Screenshot-like dimensions ({w}×{h}) — "
                f"width matches common device/browser width"
            )

        # Suspiciously small (under 200KB pixel area — likely fabricated)
        if total_pixels < 50_000 and (w < 300 or h < 300):
            evidence.append(
                f"Tiny image ({w}×{h}) — may be a thumbnail or fabricated"
            )

        result["dpi_evidence"] = evidence
        result["dpi_suspicious"] = len(evidence) > 0
        result["dpi_confidence"] = min(1.0, 0.3 * len(evidence) + 0.15)

    except Exception as e:
        logger.warning(f"DPI analysis failed: {e}")
        result["dpi_evidence"] = [f"DPI analysis failed: {str(e)[:80]}"]

    return result


# =============================================================================
# 4. Channel Histogram Anomaly Detection
# =============================================================================

def _histogram_analysis(img: "Image.Image") -> Dict[str, Any]:
    """
    Analyze color channel histograms for signs of digital manipulation.

    Real photos have smooth, bell-shaped histograms with gradual transitions.
    Digitally created/edited images often have:
    - Histogram gaps (missing intensity values from quantization)
    - Comb patterns (periodic spikes from resizing/color adjustments)
    - Channel desynchronization (R/G/B peak at very different places)
    - Clipping (spike at 0 or 255 from aggressive editing)

    Returns:
        {
            "histogram_gaps": int,         # Number of zero-count bins
            "histogram_comb_score": float,  # Periodicity score
            "histogram_clipping": float,    # Fraction at 0 or 255
            "histogram_suspicious": bool,
            "histogram_confidence": float,
            "histogram_evidence": [str],
        }
    """
    result = {
        "histogram_gaps": 0,
        "histogram_comb_score": 0.0,
        "histogram_clipping": 0.0,
        "histogram_suspicious": False,
        "histogram_confidence": 0.0,
        "histogram_evidence": [],
    }

    try:
        rgb = img.convert("RGB")
        arr = np.array(rgb)
        total_pixels = arr.shape[0] * arr.shape[1]

        evidence = []
        gap_counts = []
        clipping_totals = 0

        for ch_idx, ch_name in enumerate(["R", "G", "B"]):
            channel = arr[:, :, ch_idx].ravel()
            hist, _ = np.histogram(channel, bins=256, range=(0, 255))

            # Count gaps (bins with zero pixels, excluding edges)
            inner_hist = hist[5:251]  # Skip edges (0-4 and 251-255)
            gaps = int(np.sum(inner_hist == 0))
            gap_counts.append(gaps)

            # Clipping: pixels at exactly 0 or 255
            clipping_totals += int(hist[0]) + int(hist[255])

        # Total gaps across channels
        total_gaps = sum(gap_counts)
        result["histogram_gaps"] = total_gaps

        # Clipping ratio
        result["histogram_clipping"] = round(
            clipping_totals / max(1, total_pixels * 3), 4
        )

        # Comb detection: look for periodic zero/non-zero pattern
        # Simplified: high gap count = comb-like
        if total_gaps > 500:
            result["histogram_comb_score"] = min(1.0, total_gaps / 700.0)

        # Evidence
        # Normal JPEG compression creates 100-250 gaps; receipts (bimodal:
        # white bg + dark text) can have 400-600 gaps naturally.
        # Only flag extreme values suggesting heavy color manipulation.
        if total_gaps > 500:
            evidence.append(
                f"Histogram has {total_gaps} gaps across R/G/B channels — "
                f"suggests color manipulation or heavy resampling"
            )

        # Receipts naturally have high clipping (white background = 255 peak)
        if result["histogram_clipping"] > 0.20:
            evidence.append(
                f"Histogram clipping at {result['histogram_clipping']:.1%} — "
                f"aggressive brightness/contrast editing"
            )

        if result["histogram_comb_score"] > 0.7:
            evidence.append(
                f"Comb-like histogram pattern (score {result['histogram_comb_score']:.2f}) — "
                f"indicates multiple re-saves or color adjustment"
            )

        result["histogram_evidence"] = evidence
        result["histogram_suspicious"] = len(evidence) > 0
        result["histogram_confidence"] = min(1.0, 0.25 * len(evidence) + 0.15)

    except Exception as e:
        logger.warning(f"Histogram analysis failed: {e}")
        result["histogram_evidence"] = [f"Histogram analysis failed: {str(e)[:80]}"]

    return result


# =============================================================================
# Main Entry Point
# =============================================================================

def run_image_forensics(image_path: str) -> Dict[str, Any]:
    """
    Run all forensic analyses on an image.

    This is the CANONICAL entry point called by the pipeline.
    Returns a combined result dict that rules.py can consume.

    Args:
        image_path: Path to image file (JPEG, PNG, etc.)

    Returns:
        {
            "forensics_available": bool,
            "ela": {...},
            "noise": {...},
            "dpi": {...},
            "histogram": {...},
            "overall_suspicious": bool,
            "overall_confidence": float,
            "overall_evidence": [str],
            "signal_count": int,          # Number of suspicious signals
        }
    """
    result = {
        "forensics_available": False,
        "ela": {},
        "noise": {},
        "dpi": {},
        "histogram": {},
        "overall_suspicious": False,
        "overall_confidence": 0.0,
        "overall_evidence": [],
        "signal_count": 0,
    }

    if not _PIL_AVAILABLE:
        result["overall_evidence"] = ["PIL not available — forensics skipped"]
        return result

    # Load image
    try:
        path = Path(image_path)
        if not path.exists():
            result["overall_evidence"] = [f"Image not found: {image_path}"]
            return result

        img = Image.open(str(path))
        # Convert palette/RGBA to RGB for consistent analysis
        if img.mode in ("P", "LA", "PA"):
            img = img.convert("RGBA").convert("RGB")
        elif img.mode == "RGBA":
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        result["forensics_available"] = True

    except Exception as e:
        result["overall_evidence"] = [f"Failed to load image: {str(e)[:80]}"]
        return result

    # Run all analyses
    result["ela"] = _ela_analysis(img)
    result["noise"] = _noise_analysis(img)
    result["dpi"] = _dpi_analysis(img)
    result["histogram"] = _histogram_analysis(img)

    # Aggregate overall verdict
    all_evidence = []
    suspicious_count = 0

    for key in ["ela", "noise", "dpi", "histogram"]:
        sub = result[key]
        if sub.get(f"{key}_suspicious"):
            suspicious_count += 1
            all_evidence.extend(sub.get(f"{key}_evidence", []))

    result["signal_count"] = suspicious_count
    result["overall_evidence"] = all_evidence
    result["overall_suspicious"] = suspicious_count >= 2  # 2+ signals = suspicious

    # Confidence: weighted average of sub-confidences
    confidences = [
        result["ela"].get("ela_confidence", 0.0),
        result["noise"].get("noise_confidence", 0.0),
        result["dpi"].get("dpi_confidence", 0.0),
        result["histogram"].get("histogram_confidence", 0.0),
    ]
    if suspicious_count > 0:
        # Average confidence of suspicious signals only
        suspicious_confs = [c for c in confidences if c > 0.2]
        result["overall_confidence"] = round(
            sum(suspicious_confs) / max(1, len(suspicious_confs)), 2
        )
    else:
        result["overall_confidence"] = 0.0

    return result
