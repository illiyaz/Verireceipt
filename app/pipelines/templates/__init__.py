"""
Receipt Template Matching Module

Provides template-based extraction for known receipt formats.
Supports:
- SROIE dataset templates (auto-generated)
- Custom user templates (YAML config)
- Template fingerprinting and matching

Usage:
    # Get template hints before extraction
    from app.pipelines.templates import get_template_hints
    hints = get_template_hints(ocr_lines)
    
    # Enhance extraction result with template matching
    from app.pipelines.templates import enhance_extraction
    enhanced = enhance_extraction(ocr_lines, extraction_result)
    
    # Add custom template
    python scripts/setup_templates.py --add-custom receipt.txt --name "My Store"
"""

from .fingerprint import TemplateFingerprint, compute_fingerprint
from .matcher import TemplateMatcher, match_template
from .registry import TemplateRegistry, get_registry
from .integration import (
    TemplateEnhancer,
    get_enhancer,
    enhance_extraction,
    get_template_hints,
)

__all__ = [
    "TemplateFingerprint",
    "compute_fingerprint",
    "TemplateMatcher", 
    "match_template",
    "TemplateRegistry",
    "get_registry",
    "TemplateEnhancer",
    "get_enhancer",
    "enhance_extraction",
    "get_template_hints",
]
