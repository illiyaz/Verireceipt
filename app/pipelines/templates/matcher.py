"""
Template Matcher

Matches receipt text against known templates using fingerprint similarity.
Returns best matching template with confidence score.
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import logging

from .fingerprint import (
    TemplateFingerprint,
    compute_fingerprint,
    AMOUNT_PATTERN,
    TAX_KEYWORDS,
    SUBTOTAL_KEYWORDS,
    TOTAL_KEYWORDS,
)

logger = logging.getLogger(__name__)


@dataclass
class TemplateMatch:
    """Result of template matching."""
    template: TemplateFingerprint
    confidence: float
    match_details: Dict[str, float]
    extraction_hints: Dict[str, str]
    
    def to_dict(self) -> Dict:
        return {
            "template_id": self.template.template_id,
            "template_name": self.template.template_name,
            "confidence": round(self.confidence, 3),
            "match_details": {k: round(v, 3) for k, v in self.match_details.items()},
            "extraction_hints": self.extraction_hints,
        }


class TemplateMatcher:
    """
    Matches receipt text against a library of known templates.
    
    Uses weighted feature matching:
    - Keyword overlap (merchant, header, footer)
    - Structural similarity (line count, layout)
    - Pattern matching (dates, amounts, separators)
    """
    
    # Feature weights for matching
    WEIGHTS = {
        "merchant_keywords": 0.25,
        "header_keywords": 0.10,
        "footer_keywords": 0.10,
        "line_count": 0.10,
        "amount_count": 0.10,
        "has_tax": 0.08,
        "has_subtotal": 0.07,
        "has_total": 0.05,
        "has_time": 0.05,
        "has_separator": 0.05,
        "has_table": 0.05,
    }
    
    def __init__(self, templates: List[TemplateFingerprint]):
        """
        Initialize matcher with template library.
        
        Args:
            templates: List of known template fingerprints
        """
        self.templates = templates
        self._index_by_keyword: Dict[str, List[TemplateFingerprint]] = {}
        self._build_index()
    
    def _build_index(self):
        """Build keyword index for fast lookup."""
        for template in self.templates:
            for kw in template.merchant_keywords:
                if kw not in self._index_by_keyword:
                    self._index_by_keyword[kw] = []
                self._index_by_keyword[kw].append(template)
    
    def match(
        self,
        lines: List[str],
        top_k: int = 3,
        min_confidence: float = 0.5
    ) -> List[TemplateMatch]:
        """
        Match receipt text against known templates.
        
        Args:
            lines: OCR text lines from receipt
            top_k: Return top K matches
            min_confidence: Minimum confidence threshold
        
        Returns:
            List of TemplateMatch objects, sorted by confidence
        """
        if not lines or not self.templates:
            return []
        
        # Compute fingerprint of input
        try:
            input_fp = compute_fingerprint(lines, source="input")
        except ValueError:
            return []
        
        # Score each template
        matches = []
        for template in self.templates:
            score, details = self._compute_similarity(input_fp, template)
            if score >= min_confidence:
                matches.append(TemplateMatch(
                    template=template,
                    confidence=score,
                    match_details=details,
                    extraction_hints=template.extraction_hints,
                ))
        
        # Sort by confidence
        matches.sort(key=lambda m: m.confidence, reverse=True)
        
        return matches[:top_k]
    
    def match_best(
        self,
        lines: List[str],
        min_confidence: float = 0.5
    ) -> Optional[TemplateMatch]:
        """
        Get best matching template.
        
        Args:
            lines: OCR text lines
            min_confidence: Minimum confidence threshold
        
        Returns:
            Best TemplateMatch or None if no match above threshold
        """
        matches = self.match(lines, top_k=1, min_confidence=min_confidence)
        return matches[0] if matches else None
    
    def _compute_similarity(
        self,
        input_fp: TemplateFingerprint,
        template: TemplateFingerprint
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute similarity score between input and template fingerprints.
        
        Returns:
            (overall_score, feature_scores_dict)
        """
        scores = {}
        
        # Keyword similarity (Jaccard)
        scores["merchant_keywords"] = self._jaccard_similarity(
            input_fp.merchant_keywords, template.merchant_keywords
        )
        scores["header_keywords"] = self._jaccard_similarity(
            input_fp.header_keywords, template.header_keywords
        )
        scores["footer_keywords"] = self._jaccard_similarity(
            input_fp.footer_keywords, template.footer_keywords
        )
        
        # Line count similarity
        scores["line_count"] = self._range_similarity(
            input_fp.line_count_range[0],  # Use actual count
            template.line_count_range
        )
        
        # Amount count similarity
        scores["amount_count"] = self._range_similarity(
            input_fp.amount_count_range[0],
            template.amount_count_range
        )
        
        # Boolean feature matches
        scores["has_tax"] = 1.0 if input_fp.has_tax_line == template.has_tax_line else 0.5
        scores["has_subtotal"] = 1.0 if input_fp.has_subtotal_line == template.has_subtotal_line else 0.5
        scores["has_total"] = 1.0 if input_fp.has_total_line == template.has_total_line else 0.5
        scores["has_time"] = 1.0 if input_fp.has_time == template.has_time else 0.5
        scores["has_separator"] = 1.0 if input_fp.has_separator_lines == template.has_separator_lines else 0.5
        scores["has_table"] = 1.0 if input_fp.has_table_structure == template.has_table_structure else 0.5
        
        # Compute weighted average
        total_score = sum(
            scores[feature] * weight
            for feature, weight in self.WEIGHTS.items()
        )
        
        return total_score, scores
    
    @staticmethod
    def _jaccard_similarity(set1: set, set2: set) -> float:
        """Compute Jaccard similarity between two sets."""
        if not set1 and not set2:
            return 0.5  # Neutral if both empty
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def _range_similarity(value: int, range_tuple: Tuple[int, int]) -> float:
        """Compute similarity based on value being within range."""
        min_val, max_val = range_tuple
        if min_val <= value <= max_val:
            return 1.0
        # Gradual falloff outside range
        if value < min_val:
            distance = min_val - value
        else:
            distance = value - max_val
        # Score decreases by 0.1 for each unit outside range
        return max(0.0, 1.0 - (distance * 0.1))


def match_template(
    lines: List[str],
    templates: List[TemplateFingerprint],
    min_confidence: float = 0.5
) -> Optional[TemplateMatch]:
    """
    Convenience function to match receipt against templates.
    
    Args:
        lines: OCR text lines
        templates: List of template fingerprints
        min_confidence: Minimum confidence threshold
    
    Returns:
        Best TemplateMatch or None
    """
    matcher = TemplateMatcher(templates)
    return matcher.match_best(lines, min_confidence)
