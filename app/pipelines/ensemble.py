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
    
    def build_ensemble_verdict(
        self,
        results: Dict[str, Any],
        converged_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build ensemble verdict by converging all signals.
        
        Strategy:
        1. Vision LLM: Primary authenticity filter
        2. Converged Data: Use best extraction from all engines
        3. Rule-Based: Validate using converged data (not raw OCR)
        4. Agreement Score: Higher confidence when engines agree
        
        Returns:
            Ensemble verdict with reasoning
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
        
        # Ensure vision_reasoning is a string
        if not isinstance(vision_reasoning, str):
            vision_reasoning = str(vision_reasoning) if vision_reasoning else ""
        
        # Check for explicit fraud indicators in Vision LLM
        fraud_keywords = ["fake", "edited", "manipulated", "screenshot", "receiptfaker", "watermark"]
        has_fraud_indicator = any(keyword in vision_reasoning.lower() for keyword in fraud_keywords)
        
        if has_fraud_indicator:
            verdict["final_label"] = "fake"
            verdict["confidence"] = max(0.85, vision_confidence)
            verdict["recommended_action"] = "reject"
            verdict["reasoning"].append("🚨 Vision LLM detected fraud indicators:")
            verdict["reasoning"].append(f"   {vision_reasoning}")
            return verdict
        
        # Step 2: Calculate agreement score
        agreement_score = self._calculate_agreement(results, converged_data)
        verdict["agreement_score"] = agreement_score
        
        # Step 3: Get Rule-Based verdict (should use converged data)
        rule_label = results.get("rule_based", {}).get("label", "unknown")
        rule_score = results.get("rule_based", {}).get("score", 0.5)
        rule_reasons = results.get("rule_based", {}).get("reasons", [])
        
        # Step 3.5: Check for CRITICAL fraud indicators that override Vision LLM
        # These are high-confidence signals that should not be overridden
        has_critical_indicator = False
        critical_reasons = []
        
        print(f"\n🔍 Checking for critical indicators in {len(rule_reasons)} reasons...")
        for reason in rule_reasons:
            print(f"   Checking: {reason[:80]}...")
            # Check for suspicious software (iLovePDF, Canva, etc.)
            if "Suspicious Software Detected" in reason or "iLovePDF" in reason or "Canva" in reason:
                has_critical_indicator = True
                critical_reasons.append(reason)
                print(f"   ✅ CRITICAL: Suspicious software detected!")
            # Check for date manipulation (various phrasings)
            elif "AFTER the receipt date" in reason or "Suspicious Date Gap" in reason or "backdated" in reason.lower():
                has_critical_indicator = True
                critical_reasons.append(reason)
                print(f"   ✅ CRITICAL: Date manipulation detected!")
        
        print(f"\n🚨 Critical indicators found: {has_critical_indicator}")
        print(f"   Total critical reasons: {len(critical_reasons)}")
        
        # Step 4: Converge signals
        if vision_verdict == "real" and vision_confidence > 0.8:
            if rule_label == "real" or rule_score < 0.3:
                # Both agree: REAL
                verdict["final_label"] = "real"
                verdict["confidence"] = min(0.95, 0.80 + (agreement_score * 0.15))
                verdict["recommended_action"] = "approve"
                verdict["reasoning"].append(f"✅ Vision LLM confirms authenticity ({vision_confidence*100:.0f}% confidence)")
                verdict["reasoning"].append(f"✅ Rule-Based validation passed (score: {rule_score*100:.0f}%)")
                if agreement_score > 0.7:
                    verdict["reasoning"].append(f"✅ High agreement across engines ({agreement_score*100:.0f}%)")
            
            elif rule_label == "fake" or rule_score > 0.7:
                # Conflict: Vision says real, Rules say fake
                
                # CRITICAL: If we have critical fraud indicators, ALWAYS flag as fake
                if has_critical_indicator:
                    verdict["final_label"] = "fake"
                    verdict["confidence"] = 0.85
                    verdict["recommended_action"] = "reject"
                    verdict["reasoning"].append("🚨 CRITICAL FRAUD INDICATORS DETECTED")
                    verdict["reasoning"].append(f"❌ Rule-Based: {rule_label} ({rule_score*100:.0f}%)")
                    for reason in critical_reasons:
                        verdict["reasoning"].append(f"   • {reason}")
                    verdict["reasoning"].append(f"⚠️ Vision LLM says 'real' but critical indicators override this assessment")
                
                # Check if it's likely an OCR error
                elif converged_data.get("total") and converged_data.get("confidence", {}).get("total", 0) > 0.6:
                    # We have good extraction data - likely OCR error in Rule-Based
                    verdict["final_label"] = "suspicious"
                    verdict["confidence"] = 0.65
                    verdict["recommended_action"] = "human_review"
                    verdict["reasoning"].append("⚠️ Conflicting signals detected")
                    verdict["reasoning"].append(f"✅ Vision LLM: {vision_verdict} ({vision_confidence*100:.0f}%)")
                    verdict["reasoning"].append(f"❌ Rule-Based: {rule_label} ({rule_score*100:.0f}%)")
                    verdict["reasoning"].append(f"💡 Advanced extraction successful - possible OCR error in Rule-Based")
                    verdict["reasoning"].append(f"   Extracted Total: {converged_data['total']} (from {converged_data['sources'].get('total', 'N/A')})")
                else:
                    # No good extraction - trust Rule-Based
                    verdict["final_label"] = "fake"
                    verdict["confidence"] = 0.80
                    verdict["recommended_action"] = "reject"
                    verdict["reasoning"].append("❌ Rule-Based detected fraud indicators")
                    for reason in rule_reasons[:3]:
                        verdict["reasoning"].append(f"   • {reason}")
            else:
                # Moderate signals
                verdict["final_label"] = "suspicious"
                verdict["confidence"] = 0.70
                verdict["recommended_action"] = "human_review"
                verdict["reasoning"].append("⚠️ Moderate confidence signals")
        
        elif vision_verdict == "fake" or vision_confidence < 0.5:
            # Vision LLM uncertain or says fake
            verdict["final_label"] = "fake"
            verdict["confidence"] = 0.85
            verdict["recommended_action"] = "reject"
            verdict["reasoning"].append(f"❌ Vision LLM: {vision_verdict} ({vision_confidence*100:.0f}%)")
            if rule_label == "fake":
                verdict["reasoning"].append("❌ Rule-Based confirms fraud indicators")
        
        else:
            # Default: suspicious
            verdict["final_label"] = "suspicious"
            verdict["confidence"] = 0.60
            verdict["recommended_action"] = "human_review"
            verdict["reasoning"].append("⚠️ Insufficient confidence for automatic decision")
        
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
