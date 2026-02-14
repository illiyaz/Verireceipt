"""
Template Integration with Extraction Pipeline

ARCHITECTURE NOTE:
    Template matching is an ENHANCEMENT LAYER, not a replacement for core extraction.
    The core extraction logic in features.py (the "mental model") ALWAYS runs first.
    
    Flow:
    1. Core extraction runs (features.py) → produces base result
    2. Template matching tries to identify known formats
    3. If template matches → boost confidence, validate results
    4. If NO template matches → core extraction result used as-is (fallback)
    
    This ensures:
    - New/unknown receipts still get extracted via heuristics
    - Known templates get confidence boosts
    - No extraction is blocked by missing templates

Provides hooks for using template matching to enhance extraction:
- Pre-extraction: Identify template for extraction hints
- Post-extraction: Validate results against template expectations
- Confidence boost: Increase confidence when template matches
"""

import logging
from typing import List, Dict, Optional, Any, Tuple

from .registry import get_registry, TemplateRegistry
from .matcher import TemplateMatcher, TemplateMatch
from .fingerprint import TemplateFingerprint

logger = logging.getLogger(__name__)


class TemplateEnhancer:
    """
    Enhances extraction using template matching.
    
    Usage:
        enhancer = TemplateEnhancer()
        
        # Pre-extraction: Get hints
        hints = enhancer.get_extraction_hints(lines)
        
        # Post-extraction: Validate and boost confidence
        result = enhancer.enhance_result(lines, extraction_result)
    """
    
    # Confidence boosts for template matches
    CONFIDENCE_BOOST = {
        "high": 0.15,    # Template match > 0.8
        "medium": 0.10,  # Template match 0.6-0.8
        "low": 0.05,     # Template match 0.5-0.6
    }
    
    def __init__(self, registry: Optional[TemplateRegistry] = None):
        """
        Initialize template enhancer.
        
        Args:
            registry: Optional custom registry, uses global if not provided
        """
        self.registry = registry or get_registry()
        self._matcher: Optional[TemplateMatcher] = None
    
    @property
    def matcher(self) -> TemplateMatcher:
        """Lazy-load matcher with current templates."""
        if self._matcher is None:
            templates = self.registry.get_all()
            self._matcher = TemplateMatcher(templates)
        return self._matcher
    
    def get_extraction_hints(
        self,
        lines: List[str],
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Get extraction hints from template matching.
        
        Args:
            lines: OCR text lines
            min_confidence: Minimum template match confidence
        
        Returns:
            Dict with hints for extraction:
            - template_id: Matched template ID
            - template_name: Matched template name
            - confidence: Match confidence
            - hints: Template-specific extraction hints
            - expected_entities: Expected entity presence
        """
        if not self.registry.count():
            return {"template_match": False, "reason": "no_templates_loaded"}
        
        match = self.matcher.match_best(lines, min_confidence)
        
        if not match:
            return {"template_match": False, "reason": "no_match_above_threshold"}
        
        return {
            "template_match": True,
            "template_id": match.template.template_id,
            "template_name": match.template.template_name,
            "confidence": match.confidence,
            "hints": match.extraction_hints,
            "expected_entities": {
                "has_tax": match.template.has_tax_line,
                "has_subtotal": match.template.has_subtotal_line,
                "has_total": match.template.has_total_line,
                "has_time": match.template.has_time,
            },
            "match_details": match.match_details,
        }
    
    def enhance_result(
        self,
        lines: List[str],
        extraction_result: Dict[str, Any],
        min_template_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Enhance extraction result using template matching.
        
        Applies confidence boosts and validation based on template match.
        
        Args:
            lines: OCR text lines
            extraction_result: Raw extraction result dict
            min_template_confidence: Minimum template match confidence
        
        Returns:
            Enhanced extraction result with:
            - template_evidence: Template matching evidence
            - confidence adjustments: Boosted confidences
        """
        result = extraction_result.copy()
        
        # Get template match
        hints = self.get_extraction_hints(lines, min_template_confidence)
        result["template_evidence"] = hints
        
        if not hints.get("template_match"):
            return result
        
        template_confidence = hints["confidence"]
        
        # Determine boost level
        if template_confidence >= 0.8:
            boost = self.CONFIDENCE_BOOST["high"]
        elif template_confidence >= 0.6:
            boost = self.CONFIDENCE_BOOST["medium"]
        else:
            boost = self.CONFIDENCE_BOOST["low"]
        
        # Apply confidence boosts to entities
        result["template_confidence_boost"] = boost
        
        # Boost merchant confidence if template matched
        if "merchant_confidence" in result:
            original = result["merchant_confidence"]
            result["merchant_confidence"] = min(1.0, original + boost)
            result["merchant_confidence_original"] = original
        
        # Boost total confidence if expected and found
        if hints["expected_entities"].get("has_total") and "total" in result:
            if "total_confidence" in result:
                original = result["total_confidence"]
                result["total_confidence"] = min(1.0, original + boost)
                result["total_confidence_original"] = original
        
        # Validate against expected entities
        validation = self._validate_against_template(result, hints)
        result["template_validation"] = validation
        
        return result
    
    def _validate_against_template(
        self,
        result: Dict[str, Any],
        hints: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate extraction result against template expectations."""
        validation = {
            "matches": [],
            "mismatches": [],
            "warnings": [],
        }
        
        expected = hints.get("expected_entities", {})
        
        # Check tax
        if expected.get("has_tax"):
            if result.get("tax") or result.get("tax_amount"):
                validation["matches"].append("tax_expected_and_found")
            else:
                validation["warnings"].append("tax_expected_but_not_found")
        
        # Check subtotal
        if expected.get("has_subtotal"):
            if result.get("subtotal"):
                validation["matches"].append("subtotal_expected_and_found")
            else:
                validation["warnings"].append("subtotal_expected_but_not_found")
        
        # Check total
        if expected.get("has_total"):
            if result.get("total"):
                validation["matches"].append("total_expected_and_found")
            else:
                validation["mismatches"].append("total_expected_but_not_found")
        
        return validation
    
    def suggest_template(
        self,
        lines: List[str],
        merchant_name: Optional[str] = None
    ) -> Optional[TemplateFingerprint]:
        """
        Suggest creating a new template from receipt.
        
        Useful when no good template match is found.
        
        Args:
            lines: OCR text lines
            merchant_name: Optional known merchant name
        
        Returns:
            Suggested template fingerprint or None
        """
        from .fingerprint import compute_fingerprint
        
        # Check if good match already exists
        match = self.matcher.match_best(lines, min_confidence=0.7)
        if match:
            logger.debug(f"Good template match exists: {match.template.template_id}")
            return None
        
        # Generate new template suggestion
        template_name = merchant_name or "New Template"
        fp = compute_fingerprint(
            lines,
            template_name=template_name,
            source="suggested"
        )
        
        return fp


# Global enhancer instance
_enhancer: Optional[TemplateEnhancer] = None


def get_enhancer() -> TemplateEnhancer:
    """Get the global template enhancer."""
    global _enhancer
    if _enhancer is None:
        _enhancer = TemplateEnhancer()
    return _enhancer


def enhance_extraction(
    lines: List[str],
    extraction_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convenience function to enhance extraction with template matching.
    
    Args:
        lines: OCR text lines
        extraction_result: Raw extraction result
    
    Returns:
        Enhanced extraction result
    """
    return get_enhancer().enhance_result(lines, extraction_result)


def get_template_hints(lines: List[str]) -> Dict[str, Any]:
    """
    Convenience function to get template hints before extraction.
    
    Args:
        lines: OCR text lines
    
    Returns:
        Template hints dict
    """
    return get_enhancer().get_extraction_hints(lines)
