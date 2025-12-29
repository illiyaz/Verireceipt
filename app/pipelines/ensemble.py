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
import re  
from app.pipelines.rules import _parse_date_best_effort 

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
        # Common non-merchant labels that OCR/extractors frequently confuse as merchant names
        self._MERCHANT_LABEL_BLACKLIST = {
            "invoice", "receipt", "tax invoice", "bill", "statement", "order", "total",
            "subtotal", "amount", "amount due", "balance due", "due", "paid",
            "date", "customer", "vendor", "merchant", "payment",
        }

    def _looks_like_label_merchant(self, merchant: Any) -> bool:
        """Return True if the extracted 'merchant' looks like a field label, not a business name."""
        if merchant is None:
            return True
        s = str(merchant).strip()
        if not s:
            return True

        s_norm = re.sub(r"\s+", " ", s).strip().lower()

        # Exact blacklist matches
        if s_norm in self._MERCHANT_LABEL_BLACKLIST:
            return True

        # Very short generic tokens
        if len(s_norm) <= 3 and s_norm.isalpha():
            return True

        # Starts with common label patterns
        if re.match(r"^(invoice|receipt|tax invoice|bill|statement)\b", s_norm):
            return True

        # Looks like a key-value label rather than a name
        if re.match(r"^(merchant|vendor|customer|date|total|subtotal|amount)\s*[:\-]", s_norm):
            return True

        return False

    def _select_best_merchant_candidate(
        self,
        merchant_candidates: List[Tuple[str, Any, float]]
    ) -> Optional[Tuple[str, Any, float]]:
        """Choose the best merchant candidate, preferring non-label-like values."""
        if not merchant_candidates:
            return None

        good = [c for c in merchant_candidates if not self._looks_like_label_merchant(c[1])]
        if good:
            return max(good, key=lambda x: x[2])

        # If everything looks label-like, fall back to highest-weight candidate
        return max(merchant_candidates, key=lambda x: x[2])
    
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
            "confidence": {},       # per-field confidences (0..1)
            "sources": {},          # per-field best source
            # Normalized overall extraction confidence (always present)
            "confidence_score": 0.70,   # float in [0,1]
            "confidence_level": "medium" # "low"|"medium"|"high"
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
            best = self._select_best_merchant_candidate(merchant_candidates)
            if best:
                source, value, weight = best
                converged["merchant"] = value
                converged["sources"]["merchant"] = source
                converged["confidence"]["merchant"] = weight

                # If we had to fall back to a label-like merchant, reduce confidence a bit
                if self._looks_like_label_merchant(value):
                    converged["confidence"]["merchant"] = max(0.10, weight - 0.15)
                    logger.info(f"⚠️ Merchant candidate looks like a label: {value!r}. Reduced confidence.")
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
            total_values = [v for v in total_values if v is not None]

            if len(total_values) >= 2 and len(set(total_values)) == 1:
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
        
        # ------------------------------------------------------------------
        # Overall extraction confidence (single consistent representation)
        # Intended to feed tf["confidence"] downstream.
        # Always provide BOTH:
        # - confidence_score: float in [0,1]
        # - confidence_level: "low"|"medium"|"high"
        # ------------------------------------------------------------------
        weights = {"merchant": 0.40, "total": 0.40, "date": 0.20}
        num = 0.0
        den = 0.0

        for k, w in weights.items():
            if converged.get(k) is None:
                continue
            c = converged.get("confidence", {}).get(k)
            if c is None:
                continue
            try:
                cv = float(c)
            except Exception:
                continue
            cv = max(0.0, min(1.0, cv))
            num += (w * cv)
            den += w

        overall = (num / den) if den > 0.0 else 0.70
        overall = max(0.0, min(1.0, overall))

        converged["confidence_score"] = overall
        converged["confidence_level"] = self._confidence_level(overall)

        # Back-compat: also expose under confidence dict
        converged.setdefault("confidence", {})
        converged["confidence"]["level"] = converged.get("confidence_level")

        return converged
    
    def _normalize_amount(self, amount: Any) -> Optional[float]:
        """Normalize amount to float for comparison"""
        if amount is None:
            return None

        # Strings: strip currency symbols, commas, and handle parentheses for negatives
        if isinstance(amount, str):
            s = amount.strip()
            if not s:
                return None

            neg = False
            if s.startswith("(") and s.endswith(")"):
                neg = True
                s = s[1:-1].strip()

            # Remove common currency symbols and separators
            s = s.replace(",", "")
            s = re.sub(r"[₹$€£¥]", "", s)
            s = s.replace("INR", "").replace("USD", "").replace("EUR", "").replace("GBP", "").replace("JPY", "")
            s = s.strip()

            try:
                v = float(s)
                return -v if neg else v
            except Exception:
                return None

        try:
            return float(amount)
        except Exception:
            return None
    def _normalize_confidence(self, v: Any, default: float = 0.0) -> float:
        """Normalize confidence into [0,1]. Accepts 0-1, 0-100, '70%', and string levels."""
        if v is None:
            return max(0.0, min(1.0, float(default)))

        if isinstance(v, str):
            s = v.strip().lower()
            if not s:
                return max(0.0, min(1.0, float(default)))
            if s in ("high", "very high"):
                return 0.90
            if s in ("medium", "med"):
                return 0.70
            if s in ("low", "very low"):
                return 0.40
            try:
                if s.endswith("%"):
                    return max(0.0, min(1.0, float(s[:-1].strip()) / 100.0))
                fv = float(s)
                if fv > 1.0:
                    fv = fv / 100.0
                return max(0.0, min(1.0, fv))
            except Exception:
                return max(0.0, min(1.0, float(default)))

        try:
            fv = float(v)
            if fv > 1.0:
                fv = fv / 100.0
            return max(0.0, min(1.0, fv))
        except Exception:
            return max(0.0, min(1.0, float(default)))
    
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

    def _new_reconciliation_event(
        self,
        code: str,
        message: str,
        evidence: Optional[Dict[str, Any]] = None,
        severity: str = "INFO"
    ) -> Dict[str, Any]:
        """Structured reconciliation/audit event that callers can persist."""
        return {
            "source": "ensemble",
            "type": "reconciliation",
            "code": code,
            "message": message,
            "evidence": evidence or {},
            "severity": severity,
        }
    
    def _confidence_level(self, score: Any) -> str:
        """Convert a numeric confidence score into a stable string level."""
        try:
            v = float(score)
        except Exception:
            v = 0.70
        v = max(0.0, min(1.0, v))
        if v >= 0.85:
            return "high"
        if v >= 0.65:
            return "medium"
        return "low"
    def _extract_doc_profile(self, results: Dict[str, Any], converged_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Best-effort doc profile extraction for audit tags (now includes geo info).
        Must never throw.
        """
        try:
            rb = (results or {}).get("rule_based", {}) or {}

            # Preferred: rules.py can attach doc profile
            doc_profile = rb.get("doc_profile") or (rb.get("debug") or {}).get("doc_profile")
            if isinstance(doc_profile, dict):
                profile = {
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
                }
                # Add geo info if available
                if "lang_guess" in doc_profile:
                    profile["lang_guess"] = doc_profile.get("lang_guess")
                    profile["lang_confidence"] = doc_profile.get("lang_confidence")
                if "geo_country_guess" in doc_profile:
                    profile["geo_country_guess"] = doc_profile.get("geo_country_guess")
                    profile["geo_confidence"] = doc_profile.get("geo_confidence")
                return profile

            # Fallback: converged data
            if isinstance(converged_data, dict):
                if converged_data.get("doc_family") or converged_data.get("doc_subtype"):
                    return {
                        "doc_family": converged_data.get("doc_family"),
                        "doc_subtype": converged_data.get("doc_subtype"),
                        "doc_profile_confidence": (
                            converged_data.get("doc_profile_confidence")
                            or converged_data.get("doc_confidence")
                            or converged_data.get("confidence_score")
                        ),
                    }

            return {
                "doc_family": None,
                "doc_subtype": None,
                "doc_profile_confidence": None,
            }

        except Exception:
            return {
                "doc_family": None,
                "doc_subtype": None,
                "doc_profile_confidence": None,
            }
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
        """ Build ensemble verdict by converging all signals."""
        verdict = {
            "final_label": "unknown",
            "confidence": 0.0,
            "recommended_action": "review",
            "reasoning": [],
            "agreement_score": 0.0,
            "converged_data": converged_data,
            "reconciliation_events": [],
        }
        
        # Ensure downstream always sees consistent extraction confidence
        if isinstance(verdict.get("converged_data"), dict):
            cd = verdict["converged_data"]
            if "confidence_score" not in cd:
                cd["confidence_score"] = cd.get("confidence", {}).get("overall", 0.70)
            if "confidence_level" not in cd:
                cd["confidence_level"] = self._confidence_level(cd.get("confidence_score", 0.70))

        # Doc-type audit tags (best-effort)
        doc_profile = self._extract_doc_profile(results, converged_data)
        verdict["reconciliation_events"].append(
            self._new_reconciliation_event(
                code="ENS_DOC_PROFILE_TAGS",
                message="Derived document profile tags for audit and downstream reconciliation.",
                evidence={
                    "doc_family": doc_profile.get("doc_family"),
                    "doc_subtype": doc_profile.get("doc_subtype"),
                    "doc_profile_confidence": doc_profile.get("doc_profile_confidence"),
                },
            )
        )

        # Step 1: Vision LLM as primary filter
        vision_verdict = results.get("vision_llm", {}).get("verdict", "unknown")
        raw_vision_confidence = results.get("vision_llm", {}).get("confidence", 0.0)
        vision_confidence = self._normalize_confidence(raw_vision_confidence, default=0.0)

        # Audit / reconciliation trace (store it!)
        verdict["reconciliation_events"].append(
            self._new_reconciliation_event(
                code="ENS_VISION_CONF_NORMALIZED",
                message="Normalized Vision LLM confidence to [0,1].",
                evidence={
                    "vision_verdict": vision_verdict,
                    "raw_vision_confidence": raw_vision_confidence,
                    "normalized_vision_confidence": vision_confidence,
                },
            )
        )

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


        # --- Surface learned-rule signals into ensemble audit (optional but recommended)
        # rules.py emits learned-rule hits as structured events with rule_id=LR_LEARNED_PATTERN.
        # Here we propagate a summarized view into ensemble reconciliation_events for auditability,
        # and also keep a summary object we can attach to ENS_FINAL_DECISION for easier querying.
        learned_rule_events = [
            e for e in (rule_events or [])
            if isinstance(e, dict) and str(e.get("rule_id", "")) == "LR_LEARNED_PATTERN"
        ]

        def _safe_float(x, default=0.0):
            try:
                return float(x)
            except Exception:
                return float(default)

        def _trim_str(x: Any, limit: int = 220) -> str:
            s = "" if x is None else str(x)
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) > limit:
                return s[: limit - 3] + "..."
            return s

        # Default summary (always present, even if empty)
        learned_summary = {
            "learned_rule_count": 0,
            "patterns_top": [],
            "total_confidence_adjustment": 0.0,
            "learned_rules_top_raw": [],
        }

        if learned_rule_events:
            patterns_top = [
                (e.get("evidence", {}) or {}).get("pattern")
                for e in learned_rule_events[:5]
            ]
            learned_rules_top_raw = [
                _trim_str(((e.get("evidence", {}) or {}).get("raw") or ""), limit=240)
                for e in learned_rule_events[:5]
            ]
            total_conf_adj = sum(
                _safe_float((e.get("evidence", {}) or {}).get("confidence_adjustment"), 0.0)
                for e in learned_rule_events
            )

            learned_summary = {
                "learned_rule_count": len(learned_rule_events),
                "patterns_top": patterns_top,
                "total_confidence_adjustment": total_conf_adj,
                "learned_rules_top_raw": learned_rules_top_raw,
            }

            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_LEARNED_RULES_APPLIED",
                    message="Learned rules contributed to rule-based scoring.",
                    evidence={
                        "learned_rule_count": learned_summary["learned_rule_count"],
                        "patterns_top": learned_summary["patterns_top"],
                        "total_confidence_adjustment": learned_summary["total_confidence_adjustment"],
                        "learned_rules_top_raw": learned_summary["learned_rules_top_raw"],
                        "doc_family": doc_profile.get("doc_family"),
                        "doc_subtype": doc_profile.get("doc_subtype"),
                        "doc_profile_confidence": doc_profile.get("doc_profile_confidence"),
                    },
                )
            )

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
            critical_count = len(critical_reasons)
        else:
            # Tag-based fallback (no regex)
            sev = self._extract_severity_reasons(rule_reasons)
            hard_fail_reasons = sev["hard_fail"]
            critical_reasons = sev["critical"]
            has_hard_fail = len(hard_fail_reasons) > 0
            has_critical_indicator = len(critical_reasons) > 0

            critical_count = len(critical_reasons)

        # Helper to emit final decision event (called before every return)
        def _emit_final_decision_event() -> None:
            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_FINAL_DECISION",
                    message="Final ensemble decision produced.",
                    evidence={
                        "final_label": verdict.get("final_label"),
                        "final_confidence": verdict.get("confidence"),
                        "recommended_action": verdict.get("recommended_action"),
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                        "rule_label": rule_label,
                        "rule_score": rule_score,
                        "critical_count": critical_count,
                        "agreement_score": agreement_score,

                        # learned rules summary
                        "learned_rule_count": (learned_summary or {}).get("learned_rule_count"),
                        "learned_patterns_top": (learned_summary or {}).get("patterns_top"),
                        "learned_total_confidence_adjustment": (learned_summary or {}).get("total_confidence_adjustment"),
                        "learned_rules_top_raw": (learned_summary or {}).get("learned_rules_top_raw"),

                        # extraction confidence
                        "converged_confidence_score": (converged_data or {}).get("confidence_score"),
                        "converged_confidence_level": (converged_data or {}).get("confidence_level"),

                        # doc profile tags
                        "doc_family": doc_profile.get("doc_family"),
                        "doc_subtype": doc_profile.get("doc_subtype"),
                        "doc_profile_confidence": doc_profile.get("doc_profile_confidence"),

                        # optional pass-through geo/lang (safe even if missing)
                        "lang_guess": doc_profile.get("lang_guess"),
                        "lang_confidence": doc_profile.get("lang_confidence"),
                        "geo_country_guess": doc_profile.get("geo_country_guess"),
                        "geo_confidence": doc_profile.get("geo_confidence"),
                    },
                )
            )

        # Step 4: Decision precedence + reconciliation
        #
        # Policy:
        # - HARD_FAIL from rules ALWAYS rejects.
        # - Otherwise, strong rule evidence rejects.
        # - If Vision is very confident "real" but rules are only moderately strong,
        #   do NOT auto-reject — mark suspicious for human review.
        # - If Vision is low-confidence, defer to rules + agreement.


        # 4A) HARD_FAIL always wins
        if has_hard_fail:
            verdict["final_label"] = "fake"
            verdict["confidence"] = self._normalize_confidence(0.93, default=0.93)
            verdict["recommended_action"] = "reject"
            lines = ["🚨 HARD FAIL: Structural inconsistencies detected"]
            for reason in hard_fail_reasons[:5]:
                lines.append(f"   • {reason}")
            lines.append("ℹ️ Note: Visual realism cannot override structural inconsistencies.")
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_HARD_FAIL_WINS",
                    message="Rule engine HARD_FAIL overrides visual assessment.",
                    evidence={
                        "rule_label": rule_label,
                        "rule_score": rule_score,
                        "hard_fail_count": len(hard_fail_reasons),
                        "hard_fail_reasons_top": hard_fail_reasons[:5],
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                        "agreement_score": agreement_score,
                    },
                )
            )
            _emit_final_decision_event()
            return verdict

        # Thresholds (tunable)
        STRONG_RULE_REJECT_SCORE = 0.85
        MODERATE_RULE_SCORE = 0.70

        # Helpful flags
        vision_is_real_strong = (vision_verdict == "real" and float(vision_confidence or 0.0) >= 0.90)
        vision_is_real = (vision_verdict == "real" and float(vision_confidence or 0.0) >= 0.80)
        vision_is_fake = (vision_verdict == "fake" and float(vision_confidence or 0.0) >= 0.70)
        vision_is_low = float(vision_confidence or 0.0) < 0.50

        rule_fake_strong = (
            rule_label == "fake"
            and (
                rule_score >= STRONG_RULE_REJECT_SCORE
                or critical_count >= 2
                or has_critical_indicator
            )
        )

        rule_fake_moderate = (
            rule_label == "fake"
            and (MODERATE_RULE_SCORE <= rule_score < STRONG_RULE_REJECT_SCORE)
            and (critical_count <= 1)
        )

        rule_realish = (rule_label == "real" or rule_score < 0.30)

        # 4B) Strong rule evidence -> reject (even if it looks real)
        if rule_fake_strong:
            verdict["final_label"] = "fake"
            verdict["confidence"] = self._normalize_confidence(0.85, default=0.85)
            verdict["recommended_action"] = "reject"
            lines = ["❌ Rule Engine detected high-risk fraud indicators"]
            bullet_reasons = critical_reasons[:5] if critical_reasons else rule_reasons[:5]
            for reason in bullet_reasons:
                lines.append(f"   • {reason}")
            if vision_is_real:
                lines.append("ℹ️ Note: Receipt may look visually authentic, but internal inconsistencies indicate fabrication.")
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_RULES_STRONG_REJECT",
                    message="Rule engine strong fraud indicators trigger rejection.",
                    evidence={
                        "rule_score": rule_score,
                        "critical_count": critical_count,
                        "critical_reasons_top": bullet_reasons[:5],
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                    },
                )
            )
            _emit_final_decision_event()
            return verdict


        # 4C) Vision says fake with decent confidence -> reject (unless rules are clearly clean)
        if vision_is_fake and not rule_realish:
            verdict["final_label"] = "fake"

            # Confidence: start from a base, then blend in vision confidence + rule score + agreement.
            # (All inputs are already normalized to [0,1])
            base = 0.70
            blended = base + (0.20 * float(vision_confidence or 0.0)) + (0.10 * float(rule_score or 0.0)) + (0.05 * float(agreement_score or 0.0))
            verdict["confidence"] = self._normalize_confidence(min(0.90, blended), default=0.80)

            verdict["recommended_action"] = "reject"

            lines = [
                f"❌ Vision LLM: fake (conf={float(vision_confidence or 0.0):.2f})",
                f"ℹ️ Rule Engine: {rule_label} (score={rule_score:.2f}, critical_count={critical_count})",
                f"ℹ️ agreement_score={agreement_score:.2f}",
            ]

            # Surface the most relevant rule reasons (critical first), if available
            bullets = (critical_reasons or rule_reasons)[:5]
            for r in bullets:
                lines.append(f"   • {r}")

            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)

            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_VISION_FAKE_REJECT",
                    message="Vision LLM indicated FAKE with decent confidence; rules were not clearly clean, so rejected.",
                    evidence={
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                        "rule_label": rule_label,
                        "rule_score": rule_score,
                        "critical_count": critical_count,
                        "critical_reasons_top": bullets[:5],
                        "agreement_score": agreement_score,
                        "converged_confidence_score": (converged_data or {}).get("confidence_score"),
                        "converged_confidence_level": (converged_data or {}).get("confidence_level"),
                        "final_confidence": verdict["confidence"],
                    },
                )
            )
            _emit_final_decision_event()
            return verdict

        # 4D) Vision/Rules conflict: Vision very confident REAL, rules only moderate -> human review
        if vision_is_real_strong and rule_fake_moderate:
            verdict["final_label"] = "suspicious"
            verdict["confidence"] = self._normalize_confidence(0.70, default=0.70)
            verdict["recommended_action"] = "human_review"
            lines = [
                "⚠️ Vision/Rules conflict: Vision is highly confident REAL, but rules flagged anomalies.",
                f"✅ Vision LLM: real (conf={float(vision_confidence or 0.0):.2f})",
                f"❌ Rule Engine: fake (score={rule_score:.2f}, critical_count={critical_count})",
            ]
            bullets = (critical_reasons or rule_reasons)[:5]
            bullet_reasons = bullets
            for r in bullets:
                lines.append(f"   • {r}")
            lines.append(f"ℹ️ agreement_score={agreement_score:.2f} (higher = more consistent extraction)")
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_VISION_RULE_CONFLICT_REVIEW",
                    message="Vision is highly confident REAL but rules flagged anomalies; routed to human review.",
                    evidence={
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                        "rule_label": rule_label,
                        "rule_score": rule_score,
                        "critical_count": critical_count,
                        "critical_reasons_top": bullet_reasons[:5],
                        "agreement_score": agreement_score,
                        "converged_confidence_score": (converged_data or {}).get("confidence_score"),
                        "converged_confidence_level": (converged_data or {}).get("confidence_level"),
                    },
                )
            )
            _emit_final_decision_event()
            return verdict

        # 4E) Both engines align on REAL (or rules are clean) -> approve
        if vision_is_real and rule_realish and not has_critical_indicator and critical_count == 0:
            verdict["final_label"] = "real"
            # Confidence when both engines align: blend Vision confidence and agreement
            blended = 0.70 + (0.15 * float(vision_confidence or 0.0)) + (0.20 * float(agreement_score or 0.0))
            verdict["confidence"] = self._normalize_confidence(min(0.95, blended), default=0.85)
            verdict["recommended_action"] = "approve"
            lines = ["✅ Vision LLM confirms authenticity", "✅ Rule Engine validation passed"]
            if agreement_score >= 0.7:
                lines.append("✅ High agreement across extraction engines")
            verdict["reasoning"] = []
            seen_lines = set()
            for l in lines:
                if l not in seen_lines:
                    verdict["reasoning"].append(l)
                    seen_lines.add(l)
            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_ALIGN_APPROVE",
                    message="Vision and rules align; approved.",
                    evidence={
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                        "rule_label": rule_label,
                        "rule_score": rule_score,
                        "critical_count": critical_count,
                        "agreement_score": agreement_score,
                        "converged_confidence_score": (converged_data or {}).get("confidence_score"),
                        "converged_confidence_level": (converged_data or {}).get("confidence_level"),
                    },
                )
            )
            _emit_final_decision_event()
            return verdict

        # 4F) Low-confidence vision: defer to rules + agreement
        if vision_is_low:
            if rule_realish and not has_critical_indicator and critical_count == 0 and agreement_score >= 0.70:
                verdict["final_label"] = "real"
                blended = 0.55 + (0.25 * float(agreement_score or 0.0)) + (0.20 * (1.0 - float(rule_score or 0.0)))
                verdict["confidence"] = self._normalize_confidence(min(0.85, blended), default=0.70)
                verdict["recommended_action"] = "approve"
                verdict["reasoning"] = [
                    "✅ Rule Engine validation passed",
                    "✅ High agreement across extraction engines",
                    "ℹ️ Vision model was low-confidence; decision based on rules + agreement.",
                ]
                verdict["reconciliation_events"].append(
                    self._new_reconciliation_event(
                        code="ENS_VISION_LOW_RULES_AGREE_APPROVE",
                        message="Vision was low-confidence; approved based on rules + high agreement.",
                        evidence={
                            "vision_verdict": vision_verdict,
                            "vision_confidence": vision_confidence,
                            "rule_label": rule_label,
                            "rule_score": rule_score,
                            "critical_count": critical_count,
                            "agreement_score": agreement_score,
                            "converged_confidence_score": (converged_data or {}).get("confidence_score"),
                            "converged_confidence_level": (converged_data or {}).get("confidence_level"),
                        },
                    )
                )
                _emit_final_decision_event()
                return verdict

            verdict["final_label"] = rule_label if rule_label in ("real", "fake", "suspicious") else "suspicious"
            review_conf = 0.45 + (0.20 * float(agreement_score or 0.0)) + (0.20 * (1.0 - float(rule_score or 0.0)))
            verdict["confidence"] = self._normalize_confidence(min(0.75, review_conf), default=0.60)
            verdict["recommended_action"] = "human_review"
            verdict["reasoning"] = [
                "⚠️ Vision model low-confidence; deferring to rule-based signals.",
                f"ℹ️ Rule label={rule_label}, score={rule_score:.2f}, critical_count={critical_count}",
            ]
            verdict["reconciliation_events"].append(
                self._new_reconciliation_event(
                    code="ENS_VISION_LOW_DEFER_REVIEW",
                    message="Vision was low-confidence; deferred to human review using rule signals.",
                    evidence={
                        "vision_verdict": vision_verdict,
                        "vision_confidence": vision_confidence,
                        "rule_label": rule_label,
                        "rule_score": rule_score,
                        "critical_count": critical_count,
                        "agreement_score": agreement_score,
                        "has_critical_indicator": has_critical_indicator,
                        "agreement_threshold": 0.70,
                        "approve_gate_passed": False,
                    },
                )
            )
            _emit_final_decision_event()
            return verdict

        # 4G) Remaining conflicts: default to human review
        verdict["final_label"] = "suspicious"
        verdict["confidence"] = self._normalize_confidence(0.65, default=0.65)
        verdict["recommended_action"] = "human_review"
        lines = [
            "⚠️ Conflicting or insufficient evidence for automatic decision",
            f"ℹ️ Vision={vision_verdict} (conf={float(vision_confidence or 0.0):.2f}), Rule={rule_label} (score={rule_score:.2f}), critical_count={critical_count}",
            f"ℹ️ agreement_score={agreement_score:.2f}",
        ]
        verdict["reasoning"] = []
        seen_lines = set()
        for l in lines:
            if l not in seen_lines:
                verdict["reasoning"].append(l)
                seen_lines.add(l)
        verdict["reconciliation_events"].append(
            self._new_reconciliation_event(
                code="ENS_DEFAULT_REVIEW",
                message="Defaulted to human review due to conflict/insufficient evidence.",
                evidence={
                    "vision_verdict": vision_verdict,
                    "vision_confidence": vision_confidence,
                    "rule_label": rule_label,
                    "rule_score": rule_score,
                    "critical_count": critical_count,
                    "agreement_score": agreement_score,
                },
            )
        )
        # Final decision audit event
        verdict["reconciliation_events"].append(
            self._new_reconciliation_event(
                code="ENS_FINAL_DECISION",
                message="Final ensemble decision produced.",
                evidence={
                    "final_label": verdict.get("final_label"),
                    "final_confidence": verdict.get("confidence"),
                    "recommended_action": verdict.get("recommended_action"),
                    "vision_verdict": vision_verdict,
                    "vision_confidence": vision_confidence,
                    "rule_label": rule_label,
                    "rule_score": rule_score,
                    "critical_count": critical_count,
                    "agreement_score": agreement_score,
                    "learned_rule_count": (learned_summary or {}).get("learned_rule_count"),
                    "learned_patterns_top": (learned_summary or {}).get("patterns_top"),
                    "learned_total_confidence_adjustment": (learned_summary or {}).get("total_confidence_adjustment"),
                    "learned_rules_top_raw": (learned_summary or {}).get("learned_rules_top_raw"),
                    "converged_confidence_score": (converged_data or {}).get("confidence_score"),
                    "converged_confidence_level": (converged_data or {}).get("confidence_level"),
                    "doc_family": doc_profile.get("doc_family"),
                    "doc_subtype": doc_profile.get("doc_subtype"),
                    "doc_profile_confidence": doc_profile.get("doc_profile_confidence"),
                },
            )
        )
        _emit_final_decision_event()
        return verdict

    
    def _calculate_agreement(
        self,
        results: Dict[str, Any],
        converged_data: Dict[str, Any]
    ) -> float:
        """
        Calculate agreement score across engines.
        Higher score = more engines agree on extracted data.
        Agreement is based on value-level matching, not just presence.
        """
        agreement_points = 0.0
        max_points = 0.0

        # -------------------------------
        # Helper normalizers
        # -------------------------------
        def _norm_text(v: Any) -> Optional[str]:
            if not v or not isinstance(v, str):
                return None
            return re.sub(r"\s+", " ", v.strip().lower())

        def _values_agree(values: List[Any], tol: float = 0.01) -> float:
            """
            Returns agreement score:
            1.0 = strong agreement
            0.8 = close agreement
            0.3 = weak disagreement
            """
            vals = [v for v in values if v is not None]
            if len(vals) < 2:
                return 0.5
            max_v = max(vals)
            min_v = min(vals)
            if max_v == min_v:
                return 1.0
            if abs(max_v - min_v) <= max(0.5, tol * max_v):
                return 0.8
            return 0.3

        # -------------------------------
        # Merchant agreement
        # -------------------------------
        merchant_values = []

        if results.get("layoutlm", {}).get("merchant"):
            merchant_values.append(_norm_text(results["layoutlm"]["merchant"]))

        if results.get("donut", {}).get("merchant"):
            merchant_values.append(_norm_text(results["donut"]["merchant"]))

        dr_merchant = results.get("donut_receipt", {}).get("merchant")
        if isinstance(dr_merchant, dict):
            merchant_values.append(_norm_text(dr_merchant.get("name")))
        elif isinstance(dr_merchant, str):
            merchant_values.append(_norm_text(dr_merchant))

        merchant_values = [v for v in merchant_values if v]
        if merchant_values:
            max_points += 1.0
            if any(merchant_values.count(v) >= 2 for v in merchant_values):
                agreement_points += 1.0
            elif len(merchant_values) == 1:
                agreement_points += 0.5

        # -------------------------------
        # Total agreement
        # -------------------------------
        total_values = []

        if results.get("layoutlm", {}).get("total"):
            total_values.append(self._normalize_amount(results["layoutlm"]["total"]))

        if results.get("donut", {}).get("total"):
            donut_total = results["donut"]["total"]
            if isinstance(donut_total, dict):
                donut_total = donut_total.get("total_price")
            total_values.append(self._normalize_amount(donut_total))

        if results.get("donut_receipt", {}).get("total"):
            total_values.append(self._normalize_amount(results["donut_receipt"]["total"]))

        total_values = [v for v in total_values if v is not None]
        if total_values:
            max_points += 1.0
            agreement_points += _values_agree(total_values)

        # -------------------------------
        # Date agreement
        # -------------------------------
        date_values = []

        if results.get("layoutlm", {}).get("date"):
            date_values.append(results["layoutlm"]["date"])

        if results.get("donut_receipt", {}).get("date"):
            date_values.append(results["donut_receipt"]["date"])

        parsed_dates = []
        for d in date_values:
            try:
                parsed = _parse_date_best_effort(d)
                if parsed:
                    parsed_dates.append(parsed.date())
            except Exception:
                continue

        if parsed_dates:
            max_points += 1.0
            if len(parsed_dates) >= 2 and len(set(parsed_dates)) == 1:
                agreement_points += 1.0
            elif len(parsed_dates) == 1:
                agreement_points += 0.5
            else:
                agreement_points += 0.3

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
