"""
Core entity types for extraction pipeline.

Contains the fundamental data structures used across all extractors:
- EntityCandidate: Represents a candidate value during extraction
- EntityResult: Represents the final extraction result with confidence
- bucket_confidence: Helper to bucket confidence scores
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EntityCandidate:
    """Generic candidate for entity extraction (merchant, total, date, etc.)"""
    value: Any  # Support both str and float for numeric entities
    score: float
    source: str  # e.g., "top_scan", "label_next_line", "uppercase_merge", "llm_picker"
    line_idx: int
    raw_line: str
    norm_line: str
    reasons: List[str] = field(default_factory=list)
    # V2 fields for ML labeling
    penalties_applied: List[Dict[str, Any]] = field(default_factory=list)  # [{"name": "buyer_zone", "delta": -6}]
    boosts_applied: List[Dict[str, Any]] = field(default_factory=list)      # [{"name": "seller_zone", "delta": 8}]
    matched_keywords: List[str] = field(default_factory=list)              # keywords that matched
    zone: str = "none"  # "seller", "buyer", "none"


@dataclass
class EntityResult:
    """Generic result for entity extraction with confidence and evidence"""
    entity: str  # e.g., "merchant", "total", "date"
    value: Optional[Any]  # Support both str and float for numeric entities
    confidence: float  # 0.0 to 1.0
    confidence_bucket: str  # "HIGH", "MEDIUM", "LOW", "NONE"
    candidates: List[EntityCandidate] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    # V2 fields for ML labeling
    schema_version: int = 1  # Will be set to 2 when using V2 features
    ml_payload: Optional[Dict[str, Any]] = None  # V2 ML labeling payload
    
    def to_ml_dict(self, doc_id: Optional[str] = None, page_count: Optional[int] = None, 
                   lang_script: Optional[str] = None, include_debug_context: bool = False) -> Dict[str, Any]:
        """Convert to stable JSON dict for ML labeling (no objects)."""
        self.schema_version = 2
        self.ml_payload = self._build_ml_payload(doc_id, page_count, lang_script, include_debug_context)
        return self.ml_payload
    
    def to_candidate_rows(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Convert to list of candidate rows for dataset generation."""
        return self._to_candidate_rows(doc_id)
    
    def _build_ml_payload(self, doc_id: Optional[str] = None, page_count: Optional[int] = None, 
                          lang_script: Optional[str] = None, include_debug_context: bool = False) -> Dict[str, Any]:
        """Build V2 ML payload for labeling and analysis."""
        
        # Build mode trace
        mode_trace = []
        
        # Current mode (strict/relaxed)
        current_mode = {
            "mode": "relaxed" if self.evidence.get("fallback_mode") == "relaxed" else "strict",
            "enabled_llm": self.evidence.get("llm_used", False),
            "winner": self.value,
            "confidence": self.confidence,
            "winner_margin": self.evidence.get("winner_margin", 0.0)
        }
        mode_trace.append(current_mode)
        
        # Add LLM mode if used
        if self.evidence.get("llm_used"):
            llm_mode = {
                "mode": "llm_tiebreak",
                "enabled_llm": True,
                "winner": self.value,
                "confidence": self.confidence,
                "winner_margin": self.evidence.get("winner_margin", 0.0),
                "llm_choice": self.evidence.get("llm_choice")
            }
            mode_trace.append(llm_mode)
        
        # Build winner object
        winner_candidate = None
        for cand in self.candidates:
            if cand.value == self.value:
                winner_candidate = cand
                break
        
        winner_obj = None
        if winner_candidate:
            winner_obj = {
                "value": winner_candidate.value,
                "line_idx": winner_candidate.line_idx,
                "score": winner_candidate.score,
                "reasons": winner_candidate.reasons,
                "source": winner_candidate.source,
                "zone": winner_candidate.zone,
                "penalties_applied": winner_candidate.penalties_applied,
                "boosts_applied": winner_candidate.boosts_applied,
                "matched_keywords": winner_candidate.matched_keywords
            }
        
        # Compute topk_gap
        topk_gap = 0.0
        if len(self.candidates) > 1 and winner_candidate:
            top3_scores = [cand.score for cand in self.candidates[:3]]
            topk_gap = winner_candidate.score - (sum(top3_scores) - winner_candidate.score) / (len(top3_scores) - 1) if len(top3_scores) > 1 else winner_candidate.score
        
        # Build feature flags
        feature_flags = {
            "in_seller_zone": any("seller_zone" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "buyer_zone_penalty_applied": any("buyer_zone" in cand.reasons or "buyer_zone_penalty" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "label_next_line_hit": any("label_next_line" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "company_name_hit": any("company_name" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "uppercase_header_hit": any("uppercase_header" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "ref_like_hit": any("ref_like" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "title_like_hit": any("title_like" in cand.reasons for cand in self.candidates if cand.value == self.value),
            "address_like_hit": any("address_like" in cand.reasons for cand in self.candidates if cand.value == self.value)
        }
        
        # Build rejection stats
        rejection_stats = {
            "symbol_only": self.evidence.get("rejections_symbol_only", 0),
            "digit_ratio": self.evidence.get("rejections_digit_ratio", 0),
            "title_blacklist": self.evidence.get("rejections_title_blacklist", 0),
            "structural_label": self.evidence.get("rejections_structural_label", 0),
            "plausibility_fail": self.evidence.get("rejections_plausibility_fail", 0)
        }
        
        # Debug context (gated)
        debug_context = None
        if include_debug_context or os.environ.get("ENTITY_EXTRACTION_DEBUG", "0").lower() in ("1", "true", "yes"):
            debug_context = {
                "first_40_lines": self.evidence.get("debug_first_40_lines", []),
                "seller_zone_lines": self.evidence.get("seller_zone_lines", []),
                "buyer_zone_lines": self.evidence.get("buyer_zone_lines", [])
            }
        
        # Build top-K candidates
        top_k = []
        for i, cand in enumerate(self.candidates[:8]):
            top_k.append({
                "rank": i + 1,
                "value": cand.value,
                "norm": cand.norm_line,
                "score": cand.score,
                "line_idx": cand.line_idx,
                "source": cand.source,
                "reasons": cand.reasons,
                "zone": cand.zone,
                "penalties_applied": cand.penalties_applied,
                "boosts_applied": cand.boosts_applied
            })
        
        payload = {
            "schema_version": 2,
            "entity": self.entity,
            "value": self.value,
            "confidence": self.confidence,
            "confidence_bucket": self.confidence_bucket,
            "doc_id": doc_id,
            "page_count": page_count,
            "lang_script": lang_script,
            "mode_trace": mode_trace,
            "winner": winner_obj,
            "winner_margin": self.evidence.get("winner_margin", 0.0),
            "topk_gap": round(topk_gap, 2),
            "candidate_count_total": self.evidence.get("total_candidates", 0),
            "candidate_count_filtered": self.evidence.get("filtered_candidates", 0),
            "top_k": top_k,
            "rejection_stats": rejection_stats,
            "feature_flags": feature_flags,
            "debug_context": debug_context,
            "labeling_fields": {
                "human_label": None,
                "labeler_notes": None,
                "error_type": None,
                "golden_case_id": None
            }
        }
        
        return payload
    
    def _to_candidate_rows(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Convert candidates to list of rows for candidate-level dataset."""
        rows = []
        for rank, cand in enumerate(self.candidates, 1):
            row = {
                "doc_id": doc_id,
                "entity": self.entity,
                "candidate_rank": rank,
                "is_winner": cand.value == self.value,
                "value": cand.value,
                "norm": cand.norm_line,
                "score": cand.score,
                "line_idx": cand.line_idx,
                "source": cand.source,
                "zone": cand.zone,
                "reasons": cand.reasons,
                "penalties_applied": cand.penalties_applied,
                "boosts_applied": cand.boosts_applied,
                "matched_keywords": cand.matched_keywords,
                "final_confidence": self.confidence if cand.value == self.value else None,
                "final_confidence_bucket": self.confidence_bucket if cand.value == self.value else None
            }
            rows.append(row)
        return rows


def bucket_confidence(conf: float) -> str:
    """Bucket confidence into HIGH/MEDIUM/LOW/NONE."""
    if conf >= 0.80:
        return "HIGH"
    elif conf >= 0.55:
        return "MEDIUM"
    elif conf > 0:
        return "LOW"
    else:
        return "NONE"
