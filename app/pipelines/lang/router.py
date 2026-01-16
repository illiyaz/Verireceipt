"""
Language pack routing logic.

Selects the most appropriate language pack(s) for a given document
based on script detection, locale hints, and confidence thresholds.
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .loader import LangPackLoader
from .detect_script import ScriptDetector
from .schema import LangPack


logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of language pack routing."""
    primary_pack: LangPack
    fallback_packs: List[LangPack]
    confidence: float
    script: str
    locale_hint: Optional[str]
    reasoning: List[str]
    
    @property
    def all_packs(self) -> List[LangPack]:
        """Get all packs (primary + fallbacks)."""
        return [self.primary_pack] + self.fallback_packs


class LangPackRouter:
    """Routes documents to appropriate language packs."""
    
    def __init__(self, loader: LangPackLoader, detector: ScriptDetector):
        """
        Initialize router.
        
        Args:
            loader: Language pack loader
            detector: Script detector
        """
        self.loader = loader
        self.detector = detector
        self._script_confidence_threshold = 0.3
        self._min_confidence_for_primary = 0.5
    
    def route_document(
        self, 
        text: str, 
        locale_hint: Optional[str] = None,
        allow_multi_pack: bool = True
    ) -> RoutingResult:
        """
        Route document to appropriate language pack(s).
        
        Args:
            text: Document text for analysis
            locale_hint: Optional locale hint (e.g., from metadata)
            allow_multi_pack: Whether to allow multiple packs for mixed-script documents
            
        Returns:
            RoutingResult with selected pack(s) and confidence
        """
        # Detect scripts
        script_summary = self.detector.get_script_summary(text)
        dominant_script = script_summary['dominant_script']
        dominant_confidence = script_summary['dominant_confidence']
        is_mixed = script_summary['is_mixed_script']
        
        reasoning = []
        
        # Try locale-based routing first
        if locale_hint:
            locale_pack = self.loader.get_pack_by_locale(locale_hint)
            if locale_pack:
                reasoning.append(f"Locale hint '{locale_hint}' matched pack '{locale_pack.id}'")
                return self._create_result(
                    primary_pack=locale_pack,
                    confidence=0.9,  # High confidence for explicit locale
                    script=dominant_script,
                    locale_hint=locale_hint,
                    reasoning=reasoning
                )
        
        # Script-based routing
        if dominant_confidence >= self._min_confidence_for_primary:
            # Strong script detection
            script_packs = self.loader.get_packs_by_script(dominant_script)
            
            if script_packs:
                reasoning.append(f"Dominant script '{dominant_script}' (confidence: {dominant_confidence:.2f})")
                
                # Choose best pack for this script
                best_pack = self._choose_best_script_pack(script_packs, text, locale_hint)
                
                # Add fallbacks if mixed script or low confidence
                fallbacks = []
                if is_mixed and allow_multi_pack:
                    fallbacks = self._get_mixed_script_fallbacks(best_pack, text)
                elif dominant_confidence < 0.7:
                    fallbacks = [self.loader.get_fallback_pack()]
                
                return self._create_result(
                    primary_pack=best_pack,
                    fallback_packs=fallbacks,
                    confidence=dominant_confidence,
                    script=dominant_script,
                    locale_hint=locale_hint,
                    reasoning=reasoning
                )
        
        # Fallback routing
        reasoning.append("Low script confidence, using fallback strategy")
        fallback_pack = self.loader.get_fallback_pack()
        
        return self._create_result(
            primary_pack=fallback_pack,
            confidence=0.2,  # Low confidence for fallback
            script=dominant_script,
            locale_hint=locale_hint,
            reasoning=reasoning
        )
    
    def _choose_best_script_pack(
        self, 
        script_packs: List[str], 
        text: str, 
        locale_hint: Optional[str]
    ) -> LangPack:
        """Choose the best pack from candidates for a script."""
        if not script_packs:
            return self.loader.get_fallback_pack()
        
        # If only one pack, use it
        if len(script_packs) == 1:
            return self.loader.get_pack(script_packs[0])
        
        # Multiple packs - score them based on keyword matches
        best_pack = None
        best_score = -1
        
        for pack_id in script_packs:
            pack = self.loader.get_pack(pack_id)
            score = self._score_pack_match(pack, text)
            
            # Boost score if locale hint matches
            if locale_hint and pack.locales and locale_hint in pack.locales:
                score += 0.3
            
            if score > best_score:
                best_score = score
                best_pack = pack
        
        return best_pack or self.loader.get_fallback_pack()
    
    def _score_pack_match(self, pack: LangPack, text: str) -> float:
        """Score how well a pack matches the given text."""
        text_lower = text.lower()
        score = 0.0
        
        # Check document title keywords
        for keyword in pack.keywords.doc_titles:
            if keyword.lower() in text_lower:
                score += 2.0
        
        # Check core keywords
        core_keywords = (
            pack.keywords.invoice + 
            pack.keywords.receipt + 
            pack.keywords.total
        )
        for keyword in core_keywords:
            if keyword.lower() in text_lower:
                score += 1.0
        
        # Check logistics keywords (bonus for logistics docs)
        for keyword in pack.keywords.logistics:
            if keyword.lower() in text_lower:
                score += 0.5
        
        # Normalize by text length to avoid bias towards longer texts
        text_words = len(text.split())
        if text_words > 0:
            score = score / (text_words / 100)  # Normalize to 100-word baseline
        
        return score
    
    def _get_mixed_script_fallbacks(self, primary_pack: LangPack, text: str) -> List[LangPack]:
        """Get fallback packs for mixed-script documents."""
        fallbacks = []
        script_candidates = self.detector.get_script_candidates(text, min_ratio=0.2)
        
        # Get packs for secondary scripts
        for script, ratio in script_candidates[1:3]:  # Top 2 secondary scripts
            if script != primary_pack.scripts[0]:  # Skip primary script
                script_packs = self.loader.get_packs_by_script(script)
                if script_packs:
                    pack = self.loader.get_pack(script_packs[0])
                    if pack and pack.id != primary_pack.id:
                        fallbacks.append(pack)
        
        # Always add English fallback if not already included
        en_pack = self.loader.get_pack('en')
        if en_pack and en_pack.id not in [p.id for p in [primary_pack] + fallbacks]:
            fallbacks.append(en_pack)
        
        return fallbacks[:2]  # Limit to 2 fallbacks
    
    def _create_result(
        self,
        primary_pack: LangPack,
        fallback_packs: Optional[List[LangPack]] = None,
        confidence: float = 0.0,
        script: str = 'latin',
        locale_hint: Optional[str] = None,
        reasoning: Optional[List[str]] = None
    ) -> RoutingResult:
        """Create a routing result."""
        return RoutingResult(
            primary_pack=primary_pack,
            fallback_packs=fallback_packs or [],
            confidence=confidence,
            script=script,
            locale_hint=locale_hint,
            reasoning=reasoning or []
        )
    
    def get_routing_stats(self, text: str) -> Dict:
        """Get detailed routing statistics for debugging."""
        script_summary = self.detector.get_script_summary(text)
        available_packs = self.loader.get_available_packs()
        
        return {
            'script_analysis': script_summary,
            'available_packs': available_packs,
            'packs_by_script': {
                script: self.loader.get_packs_by_script(script)
                for script in set(script_summary['script_counts'].keys())
            },
            'text_sample': text[:200] + '...' if len(text) > 200 else text,
        }
    
    def set_confidence_thresholds(
        self, 
        script_threshold: float = 0.3, 
        primary_threshold: float = 0.5
    ) -> None:
        """Update confidence thresholds for routing decisions."""
        self._script_confidence_threshold = script_threshold
        self._min_confidence_for_primary = primary_threshold
        logger.info(f"Updated confidence thresholds: script={script_threshold}, primary={primary_threshold}")
    
    def route_batch(
        self, 
        texts: List[str], 
        locale_hints: Optional[List[str]] = None
    ) -> List[RoutingResult]:
        """Route multiple documents efficiently."""
        results = []
        
        for i, text in enumerate(texts):
            locale_hint = locale_hints[i] if locale_hints and i < len(locale_hints) else None
            result = self.route_document(text, locale_hint)
            results.append(result)
        
        return results
