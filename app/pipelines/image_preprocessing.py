# app/pipelines/image_preprocessing.py
"""
Image preprocessing for OCR quality improvement.
Handles thermal prints, low contrast, noise, and other quality issues.
"""

from typing import Tuple, Dict, Any
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2


def detect_thermal_print(img: Image.Image) -> Tuple[bool, float]:
    """
    Detect if image is likely a thermal print receipt.
    
    Thermal prints have characteristics:
    - Low contrast (faded)
    - Grainy texture
    - Often monochrome or near-monochrome
    - Background may be yellowed/aged
    
    Returns:
        (is_thermal, confidence)
    """
    img_array = np.array(img.convert('L'))  # Convert to grayscale
    
    # Calculate metrics
    mean_brightness = np.mean(img_array)
    std_brightness = np.std(img_array)
    
    # Thermal prints often have:
    # - High mean brightness (faded, washed out) > 180
    # - Low std deviation (low contrast) < 40
    
    is_faded = mean_brightness > 180
    is_low_contrast = std_brightness < 40
    
    # Calculate color variance (thermal prints are near-monochrome)
    img_rgb = np.array(img.convert('RGB'))
    color_variance = np.mean(np.std(img_rgb, axis=2))
    is_monochrome = color_variance < 15
    
    # Score thermal likelihood
    thermal_score = 0.0
    if is_faded:
        thermal_score += 0.4
    if is_low_contrast:
        thermal_score += 0.4
    if is_monochrome:
        thermal_score += 0.2
    
    is_thermal = thermal_score >= 0.6
    
    return is_thermal, thermal_score


def enhance_thermal_print(img: Image.Image) -> Image.Image:
    """
    Enhance thermal print for better OCR.
    
    Steps:
    1. Convert to grayscale
    2. Increase contrast
    3. Denoise
    4. Sharpen
    5. Binarize (adaptive threshold)
    """
    # Convert to grayscale
    img_gray = img.convert('L')
    
    # Increase contrast
    enhancer = ImageEnhance.Contrast(img_gray)
    img_contrast = enhancer.enhance(2.0)  # 2x contrast
    
    # Convert to numpy for OpenCV processing
    img_array = np.array(img_contrast)
    
    # Denoise using bilateral filter (preserves edges)
    img_denoised = cv2.bilateralFilter(img_array, 9, 75, 75)
    
    # Adaptive thresholding (better for uneven lighting)
    img_binary = cv2.adaptiveThreshold(
        img_denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,  # Block size
        2    # C constant
    )
    
    # Convert back to PIL
    img_enhanced = Image.fromarray(img_binary)
    
    # Sharpen
    img_enhanced = img_enhanced.filter(ImageFilter.SHARPEN)
    
    return img_enhanced


def enhance_low_contrast(img: Image.Image) -> Image.Image:
    """
    Enhance low contrast images using histogram equalization.
    """
    img_gray = img.convert('L')
    img_array = np.array(img_gray)
    
    # CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img_equalized = clahe.apply(img_array)
    
    return Image.fromarray(img_equalized)


def denoise_image(img: Image.Image) -> Image.Image:
    """
    Remove noise from image using non-local means denoising.
    """
    img_array = np.array(img.convert('RGB'))
    
    # Non-local means denoising
    img_denoised = cv2.fastNlMeansDenoisingColored(img_array, None, 10, 10, 7, 21)
    
    return Image.fromarray(img_denoised)


def preprocess_for_ocr(
    img: Image.Image,
    auto_detect: bool = True,
    force_thermal: bool = False
) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Preprocess image for optimal OCR quality.
    
    Args:
        img: Input PIL Image
        auto_detect: Automatically detect image type and apply appropriate preprocessing
        force_thermal: Force thermal print preprocessing
    
    Returns:
        (preprocessed_image, metadata)
    """
    metadata = {
        "original_size": img.size,
        "original_mode": img.mode,
        "preprocessing_applied": [],
        "is_thermal_print": False,
        "thermal_confidence": 0.0,
    }
    
    # Detect thermal print
    if auto_detect or force_thermal:
        is_thermal, thermal_conf = detect_thermal_print(img)
        metadata["is_thermal_print"] = is_thermal
        metadata["thermal_confidence"] = thermal_conf
        
        if is_thermal or force_thermal:
            img = enhance_thermal_print(img)
            metadata["preprocessing_applied"].append("thermal_enhancement")
            return img, metadata
    
    # Standard preprocessing for non-thermal images
    img_gray = img.convert('L')
    img_array = np.array(img_gray)
    
    # Check if low contrast
    std_brightness = np.std(img_array)
    if std_brightness < 50:
        img = enhance_low_contrast(img)
        metadata["preprocessing_applied"].append("contrast_enhancement")
    
    # Check if noisy (high frequency content)
    # Simple noise detection: high variance in small patches
    patch_size = 10
    h, w = img_array.shape
    if h > patch_size and w > patch_size:
        patch = img_array[:patch_size, :patch_size]
        patch_variance = np.var(patch)
        if patch_variance > 1000:  # High variance = noisy
            img = denoise_image(img)
            metadata["preprocessing_applied"].append("denoising")
    
    # Light sharpening for all images
    img = img.filter(ImageFilter.SHARPEN)
    metadata["preprocessing_applied"].append("sharpening")
    
    return img, metadata


def preprocess_batch(
    images: list[Image.Image],
    auto_detect: bool = True
) -> Tuple[list[Image.Image], list[Dict[str, Any]]]:
    """
    Preprocess a batch of images.
    
    Returns:
        (preprocessed_images, metadata_list)
    """
    preprocessed = []
    metadata_list = []
    
    for img in images:
        img_processed, meta = preprocess_for_ocr(img, auto_detect=auto_detect)
        preprocessed.append(img_processed)
        metadata_list.append(meta)
    
    return preprocessed, metadata_list
