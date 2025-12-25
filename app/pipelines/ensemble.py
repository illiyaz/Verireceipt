"""
Ensemble Intelligence System for VeriReceipt

This module implements intelligent data sharing and cross-validation
between engines to build confidence through convergence.

Flow:
1. Vision LLM: High-level authenticity check (visual manipulation)
2. Advanced Extraction: DONUT/LayoutLM extract structured data
3. Rule-Based Validation: Validate extracted data with rules
4. Ensemble Verdict: Converge all signals with weighted confidence

Key Principles:
- Share extracted data between engines
- Cross-validate values (e.g., if LayoutLM says $68.89, use that in Rule-Based)
- Weight engines by reliability for specific tasks
- Build confidence through agreement
"""

from typing import Dict, Any, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class EnsembleIntelligence:
    """
    Intelligent ensemble system that converges signals from all engines.
    """
    
    def __init__(self):
        # Engine reliability weights for different tasks
        self.extraction_weights = {
            "layoutlm": 0.40,      # Best for structured extraction
            "donut": 0.35,          # Good for receipts
            "donut_receipt": 0.25,  # Specialized but limited training data
        }
        
        self.authenticity_weights = {
            "vision_llm": 0.50,     # Best for visual manipulation detection
            "rule_based": 0.30,     # Good for structural/math validation
            "layoutlm": 0.10,       # Confidence signal
            "donut": 0.10,          # Data quality signal
        }
    
    def converge_extraction(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converge extraction results from multiple engines.
        Use the most reliable engine's data for each field.
        
        Returns:
            Converged extraction with confidence scores
        """
        converged = {
            "merchant": None,
            "total": None,
            "date": None,
            "items": [],
            "confidence": {},
            "sources": {}
        }
        
        # Safety check
        if not results or not isinstance(results, dict):
            logger.warning("Invalid results passed to converge_extraction")
            return converged
        
        # Extract merchant (prefer LayoutLM > DONUT > Donut-Receipt)
        merchant_candidates = []
        if results.get("layoutlm", {}).get("merchant"):
            merchant_candidates.append(("layoutlm", results["layoutlm"]["merchant"], 0.40))
        if results.get("donut", {}).get("merchant"):
            merchant_candidates.append(("donut", results["donut"]["merchant"], 0.35))
        
        # Handle donut_receipt merchant safely (could be None or dict)
        donut_receipt_merchant = results.get("donut_receipt", {}).get("merchant")
        if donut_receipt_merchant and isinstance(donut_receipt_merchant, dict):
            if donut_receipt_merchant.get("name"):
                merchant_candidates.append(("donut_receipt", donut_receipt_merchant["name"], 0.25))
        
        if merchant_candidates:
            # Use highest weighted source
            source, value, weight = max(merchant_candidates, key=lambda x: x[2])
            converged["merchant"] = value
            converged["sources"]["merchant"] = source
            converged["confidence"]["merchant"] = weight
        
        # Extract total (prefer LayoutLM > DONUT > Donut-Receipt)
        total_candidates = []
        if results.get("layoutlm", {}).get("total"):
            total_candidates.append(("layoutlm", results["layoutlm"]["total"], 0.40))
        if results.get("donut", {}).get("total"):
            # DONUT total might be nested
            donut_total = results["donut"]["total"]
            if isinstance(donut_total, dict):
                donut_total = donut_total.get("total_price")
            if donut_total:
                total_candidates.append(("donut", donut_total, 0.35))
        if results.get("donut_receipt", {}).get("total"):
            total_candidates.append(("donut_receipt", results["donut_receipt"]["total"], 0.25))
        
        if total_candidates:
            source, value, weight = max(total_candidates, key=lambda x: x[2])
            converged["total"] = value
            converged["sources"]["total"] = source
            converged["confidence"]["total"] = weight
            
            # Cross-validate: if multiple engines agree, boost confidence
            total_values = [self._normalize_amount(t[1]) for t in total_candidates]
            if len(set(total_values)) == 1:  # All agree
                converged["confidence"]["total"] = min(0.95, weight + 0.20)
                logger.info(f"✅ Total cross-validated: {converged['total']} (all engines agree)")
        
        # Extract date (prefer LayoutLM > Donut-Receipt > DONUT)
        date_candidates = []
        if results.get("layoutlm", {}).get("date"):
            date_candidates.append(("layoutlm", results["layoutlm"]["date"], 0.40))
        if results.get("donut_receipt", {}).get("date"):
            date_candidates.append(("donut_receipt", results["donut_receipt"]["date"], 0.30))
        if results.get("donut", {}).get("date"):
            date_candidates.append(("donut", results["donut"]["date"], 0.30))
        
        if date_candidates:
            source, value, weight = max(date_candidates, key=lambda x: x[2])
            converged["date"] = value
            converged["sources"]["date"] = source
            converged["confidence"]["date"] = weight
        
        return converged
    
    def _normalize_amount(self, amount: Any) -> Optional[float]:
        """Normalize amount to float for comparison"""
        if amount is None:
            return None
        
        # Remove currency symbols and convert to float
        if isinstance(amount, str):
            amount = amount.replace('$', '').replace(',', '').strip()
            try:
                return float(amount)
            except:
                return None
        
        try:
            return float(amount)
        except:
            return None
    
    def _normalize_rule_score(self, score: Any) -> float:
        """Normalize rule score into [0,1]. Accepts 0-1 floats, 0-100 percents, or strings like '70%'."""
        if score is None:
            return 0.5

        if isinstance(score, str):
            s = score.strip()
            try:
                if s.endswith("%"):
                    v = float(s[:-1].strip()) / 100.0
                else:
                    v = float(s)
                if v > 1.0:
                    v = v / 100.0
                return max(0.0, min(1.0, v))
            except Exception:
                return 0.5

        try:
            v = float(score)
            if v > 1.0:
                v = v / 100.0
            return max(0.0, min(1.0, v))
        except Exception:
            return 0.5

    def _extract_severity_reasons(self, rule_reasons: List[str]) -> Dict[str, List[str]]:
        """Extract tagged severities from rules.py output (preferred)."""
        hard, crit, info = [], [], []
        for r in (rule_reasons or []):
            s = str(r)
            if "[HARD_FAIL]" in s:
                hard.append(s)
            elif "[CRITICAL]" in s:
                crit.append(s)
            elif "[INFO]" in s:
                info.append(s)
        return {"hard_fail": hard, "critical": crit, "info": info}
    
    def _extract_severity_from_events(self, events: Any) -> Dict[str, List[dict]]:
        """
        Extract severities from structured rule events emitted by rules.py.
        Expected event shape (dict-like):
        { "rule_id": "...", "severity": "HARD_FAIL|CRITICAL|INFO", "weight": 0.0-1.0, "evidence": {...}, "message": "..." }
        Returns dict with keys: hard_fail, critical, info (lists of event dicts).
        """
        hard, crit, info = [], [], []
        if not events:
            return {"hard_fail": hard, "critical": crit, "info": info}

        for e in events:
            if e is None:
                continue
            if isinstance(e, dict):
                ev = e
            else:
                # best-effort conversion
                try:
                    ev = e.dict()  # pydantic v1
                except Exception:
                    try:
                        ev = dict(e)
                    except Exception:
                        continue

            sev = str(ev.get("severity", "")).upper().strip()
            if sev == "HARD_FAIL":
                hard.append(ev)
            elif sev == "CRITICAL":
                crit.append(ev)
            elif sev == "INFO":
                info.append(ev)

        return {"hard_fail": hard, "critical": crit, "info": info}

    def build_ensemble_verdict(
        self,
        results: Dict[str, Any],
        converged_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build ensemble verdict by converging all signals.
        """
        verdict = {
            "final_label": "unknown",
            "confidence": 0.0,
            "recommended_action": "review",
            "reasoning": [],
            "agreement_score": 0.0,
            "converged_data": converged_data
        }

        # Step 1: Vision LLM as primary filter
        vision_verdict = results.get("vision_llm", {}).get("verdict", "unknown")
        vision_confidence = results.get("vision_llm", {}).get("confidence", 0.0)
        vision_reasoning = results.get("vision_llm", {}).get("reasoning", "")
        if not isinstance(vision_reasoning, str):
            vision_reasoning = str(vision_reasoning) if vision_reasoning else ""

        # Step 2: Calculate agreement score
        agreement_score = self._calculate_agreement(results, converged_data)
        verdict["agreement_score"] = agreement_score

        # Step 3: Get Rule-Based verdict (and structured events if provided)
        rb = results.get("rule_based", {}) or {}
        rule_label = rb.get("label", "unknown")
        raw_rule_score = rb.get("score", 0.5)
        rule_score = self._normalize_rule_score(raw_rule_score)

        rule_reasons = rb.get("reasons", []) or []
        rule_reasons = [str(r) for r in rule_reasons]

        # NEW: Prefer structured rule events (no regex). Fallback only to severity tags in reasons.
        rule_events = rb.get("events") or rb.get("rule_events") or []
        sev_events = self._extract_severity_from_events(rule_events)

        if sev_events["hard_fail"] or sev_events["critical"] or sev_events["info"]:
            # Use events as source of truth
            has_hard_fail = len(sev_events["hard_fail"]) > 0
            has_critical_indicator = len(sev_events["critical"]) > 0

            hard_fail_reasons = []
            for ev in sev_events["hard_fail"][:10]:
                rid = ev.get("rule_id", "RULE")
                msg = ev.get("message") or ev.get("reason") or ""
                hard_fail_reasons.append(f"[HARD_FAIL] {rid}: {msg}".strip())

            critical_reasons = []
            for ev in sev_events["critical"][:10]:
                rid = ev.get("rule_id", "RULE")
                msg = ev.get("message") or ev.get("reason") or ""
                critical_reasons.append(f"[CRITICAL] {rid}: {msg}".strip())
        else:
            # Tag-based fallback (no regex)
            sev = self._extract_severity_reasons(rule_reasons)
            hard_fail_reasons = sev["hard_fail"]
            critical_reasons = sev["critical"]
            has_hard_fail = len(hard_fail_reasons) > 0
            has_critical_indicator = len(critical_reasons) > 0

        critical_count = len(critical_reasons)

        # Step 4: Decision precedence
        if has_hard_fail:
            verdict["final_label"] = "fake"
            verdict["confidence"] = 0.93
            verdict["recommended_action"] = "reject"
            lines = ["🚨 HARD FAIL: Structural inconsistencies detected"]
            for reason in hard_fail_reasons[:5]:
                lines.append(f"   • {reason}")
            lines.append("ℹ️ Note: Visual realism cannot override structural inconsistencies.")
            # Deduplicate, preserve order
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            return verdict

        # Rule-based fake with high score or critical
        if rule_label == "fake" and (rule_score >= 0.7 or critical_count >= 2 or has_critical_indicator):
            verdict["final_label"] = "fake"
            verdict["confidence"] = 0.85
            verdict["recommended_action"] = "reject"
            lines = ["❌ Rule-Based detected high-risk fraud indicators"]
            # Prefer critical reasons, else fallback to rule reasons
            bullet_reasons = critical_reasons[:5] if critical_reasons else rule_reasons[:5]
            for reason in bullet_reasons:
                lines.append(f"   • {reason}")
            # If vision says real with high confidence, add note
            if vision_verdict == "real" and vision_confidence > 0.7:
                lines.append("ℹ️ Note: Receipt may look visually authentic, but internal inconsistencies indicate fabrication.")
            # Deduplicate lines
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            return verdict

        # Both vision and rule agree on real, or rule score is low
        if vision_verdict == "real" and vision_confidence > 0.8 and (rule_label == "real" or rule_score < 0.3):
            verdict["final_label"] = "real"
            verdict["confidence"] = min(0.95, 0.75 + (agreement_score * 0.20))
            verdict["recommended_action"] = "approve"
            lines = [
                "✅ Vision LLM confirms authenticity",
                "✅ Rule-Based validation passed"
            ]
            if agreement_score >= 0.7:
                lines.append("✅ High agreement across engines")
            # Deduplicate lines
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            return verdict

        
        # Conflicting: vision real (high), rule says fake but not strong
        # We do NOT auto-reject here (hard-fail / strong-rule fake already handled above).
        if (
            vision_verdict == "real"
            and vision_confidence > 0.8
            and rule_label == "fake"
            and rule_score < 0.7
            and (critical_count <= 1)
            and not has_hard_fail
        ):
            verdict["final_label"] = "suspicious"
            verdict["confidence"] = 0.65
            verdict["recommended_action"] = "human_review"

            lines = [
                "⚠️ Conflicting signals detected",
                "✅ Vision LLM: real",
                "❌ Rule-Based: fake",
                f"ℹ️ Rule score: {rule_score:.2f} (below auto-reject threshold)",
            ]

            # Add up to 3 rule reasons to help reviewers debug the conflict.
            added = 0
            seen_reason_text = set()
            for reason in rule_reasons:
                s = str(reason).strip()
                if not s:
                    continue
                # Deduplicate reasons (by text)
                if s in seen_reason_text:
                    continue
                seen_reason_text.add(s)
                lines.append(f"   • {s}")
                added += 1
                if added >= 3:
                    break

            # Deduplicate, preserve order
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            return verdict

        # Vision is fake or vision_confidence < 0.5
        if vision_verdict == "fake":
            verdict["final_label"] = "fake"
            verdict["confidence"] = 0.80
            verdict["recommended_action"] = "reject"
            lines = [f"❌ Vision LLM: {vision_verdict}"]
            if rule_label == "fake":
                lines.append("❌ Rule-Based confirms fraud indicators")
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            return verdict
        
        # Low-confidence vision: do NOT auto-reject. Defer to rules + agreement.
        if vision_confidence < 0.5:
            verdict["final_label"] = rule_label if rule_label in ("real", "fake", "suspicious") else "suspicious"

            if (rule_label == "real" or rule_score < 0.3) and not has_hard_fail and critical_count == 0 and agreement_score >= 0.7:
                verdict["final_label"] = "real"
                verdict["confidence"] = 0.70
                verdict["recommended_action"] = "approve"
                verdict["reasoning"] = [
                    "✅ Rule-Based validation passed",
                    "✅ High agreement across engines",
                    "ℹ️ Vision model was low-confidence; decision based on rules + agreement.",
                ]
                return verdict

            verdict["confidence"] = 0.60
            verdict["recommended_action"] = "human_review"
            verdict["reasoning"] = [
                "⚠️ Vision model low-confidence; deferring to rule-based signals.",
                f"ℹ️ Rule label={rule_label}, score={rule_score:.2f}, critical_count={critical_count}",
            ]
            return verdict

        # Default: suspicious
        verdict["final_label"] = "suspicious"
        verdict["confidence"] = 0.60
        verdict["recommended_action"] = "human_review"
        lines = ["⚠️ Insufficient confidence for automatic decision"]
        verdict["reasoning"] = []
        seen_lines = set()
        for l in lines:
            if l not in seen_lines:
                verdict["reasoning"].append(l)
                seen_lines.add(l)
        return verdict
    
    def _calculate_agreement(
        self,
        results: Dict[str, Any],
        converged_data: Dict[str, Any]
    ) -> float:
        """
        Calculate agreement score across engines.
        Higher score = more engines agree on extracted data.
        """
        agreement_points = 0.0
        max_points = 0.0
        
        # Check merchant agreement
        if converged_data.get("merchant"):
            max_points += 1.0
            merchant_sources = 0
            if results.get("layoutlm", {}).get("merchant"):
                merchant_sources += 1
            if results.get("donut", {}).get("merchant"):
                merchant_sources += 1
            if results.get("donut_receipt", {}).get("merchant", {}).get("name"):
                merchant_sources += 1
            
            if merchant_sources >= 2:
                agreement_points += 1.0
            elif merchant_sources == 1:
                agreement_points += 0.5
        
        # Check total agreement
        if converged_data.get("total"):
            max_points += 1.0
            total_values = []
            if results.get("layoutlm", {}).get("total"):
                total_values.append(self._normalize_amount(results["layoutlm"]["total"]))
            if results.get("donut", {}).get("total"):
                donut_total = results["donut"]["total"]
                if isinstance(donut_total, dict):
                    donut_total = donut_total.get("total_price")
                total_values.append(self._normalize_amount(donut_total))
            
            # Remove None values
            total_values = [v for v in total_values if v is not None]
            
            if len(total_values) >= 2:
                # Check if values are close (within 1%)
                if len(set(total_values)) == 1:
                    agreement_points += 1.0
                elif max(total_values) - min(total_values) < max(total_values) * 0.01:
                    agreement_points += 0.8
                else:
                    agreement_points += 0.3
            elif len(total_values) == 1:
                agreement_points += 0.5
        
        # Check date agreement
        if converged_data.get("date"):
            max_points += 1.0
            date_sources = 0
            if results.get("layoutlm", {}).get("date"):
                date_sources += 1
            if results.get("donut_receipt", {}).get("date"):
                date_sources += 1
            
            if date_sources >= 2:
                agreement_points += 1.0
            elif date_sources == 1:
                agreement_points += 0.5
        
        if max_points == 0:
            return 0.0
        
        return agreement_points / max_points


# Global instance
_ensemble = None


def get_ensemble() -> EnsembleIntelligence:
    """Get or create global ensemble instance"""
    global _ensemble
    if _ensemble is None:
        _ensemble = EnsembleIntelligence()
    return _ensemble
