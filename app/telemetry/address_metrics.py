"""
Telemetry and Metrics for Address Validation Features

Lightweight observability for address features (V1, V2.1, V2.2).
Tracks distribution, gating rates, and signal overlaps.

Design Philosophy:
- Lightweight counters/logs (no dashboards yet)
- JSON-structured output for easy parsing
- No performance impact (async-friendly)
- Privacy-safe (no PII, only aggregates)

Usage:
    from app.telemetry.address_metrics import AddressMetrics
    
    metrics = AddressMetrics()
    metrics.record_address_profile(address_profile, doc_profile_confidence)
    metrics.record_multi_address(multi_address_profile, doc_profile_confidence)
    metrics.record_consistency(merchant_address_consistency, merchant_confidence, doc_profile_confidence)
    
    # Get summary
    summary = metrics.get_summary()
"""

import json
import logging
from typing import Dict, Any, Optional
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class AddressMetrics:
    """
    Telemetry collector for address validation features.
    
    Tracks:
    - Feature distribution (classification, status)
    - Gating rates (confidence thresholds)
    - Signal overlaps (multi-address ∧ mismatch)
    - Address type distribution (PO_BOX vs STANDARD)
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self.counters = defaultdict(int)
        self.overlaps = defaultdict(int)
        self.start_time = datetime.utcnow()
        self.doc_count = 0
    
    def record_address_profile(
        self,
        address_profile: Dict[str, Any],
        doc_profile_confidence: float,
    ) -> None:
        """
        Record address_profile metrics.
        
        Tracks:
        - Classification distribution
        - Address type distribution
        - Score ranges
        
        Args:
            address_profile: Output from validate_address()
            doc_profile_confidence: Document confidence
        """
        self.doc_count += 1
        
        classification = address_profile.get("address_classification", "UNKNOWN")
        address_type = address_profile.get("address_type", "UNKNOWN")
        score = address_profile.get("address_score", 0)
        
        # Classification distribution
        self.counters[f"address_classification.{classification}"] += 1
        
        # Address type distribution
        self.counters[f"address_type.{address_type}"] += 1
        
        # Score ranges
        if score >= 6:
            self.counters["address_score.strong"] += 1
        elif score >= 4:
            self.counters["address_score.plausible"] += 1
        elif score >= 1:
            self.counters["address_score.weak"] += 1
        else:
            self.counters["address_score.none"] += 1
        
        # High-quality addresses (PLAUSIBLE or STRONG)
        if classification in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}:
            self.counters["address_quality.high"] += 1
        
        # PO Box addresses
        if address_type == "PO_BOX":
            self.counters["address_special.po_box"] += 1
    
    def record_multi_address(
        self,
        multi_address_profile: Dict[str, Any],
        doc_profile_confidence: float,
    ) -> None:
        """
        Record multi_address_profile metrics.
        
        Tracks:
        - Status distribution (SINGLE, MULTIPLE, UNKNOWN)
        - Count distribution
        - Gating rates
        
        Args:
            multi_address_profile: Output from detect_multi_address_profile()
            doc_profile_confidence: Document confidence
        """
        status = multi_address_profile.get("status", "UNKNOWN")
        count = multi_address_profile.get("count", 0)
        
        # Status distribution
        self.counters[f"multi_address.status.{status}"] += 1
        
        # Count distribution
        if count == 0:
            self.counters["multi_address.count.zero"] += 1
        elif count == 1:
            self.counters["multi_address.count.single"] += 1
        elif count == 2:
            self.counters["multi_address.count.two"] += 1
        elif count >= 3:
            self.counters["multi_address.count.three_plus"] += 1
        
        # Gating
        if status == "UNKNOWN" and doc_profile_confidence < 0.55:
            self.counters["multi_address.gated.low_doc_confidence"] += 1
        
        # Multiple addresses detected
        if status == "MULTIPLE":
            self.counters["multi_address.detected"] += 1
    
    def record_consistency(
        self,
        merchant_address_consistency: Dict[str, Any],
        merchant_confidence: float,
        doc_profile_confidence: float,
    ) -> None:
        """
        Record merchant_address_consistency metrics.
        
        Tracks:
        - Status distribution (CONSISTENT, WEAK_MISMATCH, MISMATCH, UNKNOWN)
        - Gating rates
        - Score distribution
        
        Args:
            merchant_address_consistency: Output from assess_merchant_address_consistency()
            merchant_confidence: Merchant extraction confidence
            doc_profile_confidence: Document confidence
        """
        status = merchant_address_consistency.get("status", "UNKNOWN")
        score = merchant_address_consistency.get("score", 0.0)
        
        # Status distribution
        self.counters[f"consistency.status.{status}"] += 1
        
        # Score ranges
        if score >= 0.8:
            self.counters["consistency.score.high"] += 1
        elif score >= 0.5:
            self.counters["consistency.score.medium"] += 1
        elif score > 0.0:
            self.counters["consistency.score.low"] += 1
        else:
            self.counters["consistency.score.zero"] += 1
        
        # Gating
        if status == "UNKNOWN":
            if doc_profile_confidence < 0.55:
                self.counters["consistency.gated.low_doc_confidence"] += 1
            elif merchant_confidence < 0.6:
                self.counters["consistency.gated.low_merchant_confidence"] += 1
        
        # Mismatches
        if status in {"WEAK_MISMATCH", "MISMATCH"}:
            self.counters["consistency.mismatch_detected"] += 1
    
    def record_overlap(
        self,
        multi_address_status: str,
        consistency_status: str,
        doc_subtype: str,
    ) -> None:
        """
        Record signal overlaps for pattern analysis.
        
        Tracks combinations like:
        - multi-address ∧ mismatch
        - multi-address ∧ invoice
        - mismatch ∧ invoice
        
        Args:
            multi_address_status: Status from multi_address_profile
            consistency_status: Status from merchant_address_consistency
            doc_subtype: Document subtype (INVOICE, POS_RECEIPT, etc.)
        """
        # Multi-address + mismatch
        if multi_address_status == "MULTIPLE" and consistency_status in {"WEAK_MISMATCH", "MISMATCH"}:
            self.overlaps["multi_and_mismatch"] += 1
        
        # Multi-address + invoice
        if multi_address_status == "MULTIPLE" and doc_subtype in {"INVOICE", "TAX_INVOICE", "VAT_INVOICE"}:
            self.overlaps["multi_and_invoice"] += 1
        
        # Mismatch + invoice
        if consistency_status in {"WEAK_MISMATCH", "MISMATCH"} and doc_subtype in {"INVOICE", "TAX_INVOICE", "VAT_INVOICE"}:
            self.overlaps["mismatch_and_invoice"] += 1
        
        # Triple overlap: multi + mismatch + invoice
        if (multi_address_status == "MULTIPLE" 
            and consistency_status in {"WEAK_MISMATCH", "MISMATCH"}
            and doc_subtype in {"INVOICE", "TAX_INVOICE", "VAT_INVOICE"}):
            self.overlaps["multi_and_mismatch_and_invoice"] += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get metrics summary.
        
        Returns:
            Dict with aggregated metrics and percentages
        """
        if self.doc_count == 0:
            return {"error": "No documents processed"}
        
        # Calculate percentages
        percentages = {}
        for key, count in self.counters.items():
            percentages[key] = {
                "count": count,
                "percentage": round(100 * count / self.doc_count, 2),
            }
        
        # Calculate overlap percentages
        overlap_percentages = {}
        for key, count in self.overlaps.items():
            overlap_percentages[key] = {
                "count": count,
                "percentage": round(100 * count / self.doc_count, 2),
            }
        
        # Calculate derived metrics
        high_quality_count = self.counters.get("address_quality.high", 0)
        multi_detected_count = self.counters.get("multi_address.detected", 0)
        mismatch_count = self.counters.get("consistency.mismatch_detected", 0)
        
        gated_doc_count = self.counters.get("multi_address.gated.low_doc_confidence", 0)
        gated_merchant_count = self.counters.get("consistency.gated.low_merchant_confidence", 0)
        
        return {
            "metadata": {
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "doc_count": self.doc_count,
            },
            "summary": {
                "high_quality_addresses": {
                    "count": high_quality_count,
                    "percentage": round(100 * high_quality_count / self.doc_count, 2),
                },
                "multi_address_detected": {
                    "count": multi_detected_count,
                    "percentage": round(100 * multi_detected_count / self.doc_count, 2),
                },
                "mismatch_detected": {
                    "count": mismatch_count,
                    "percentage": round(100 * mismatch_count / self.doc_count, 2),
                },
                "gated_low_doc_confidence": {
                    "count": gated_doc_count,
                    "percentage": round(100 * gated_doc_count / self.doc_count, 2),
                },
                "gated_low_merchant_confidence": {
                    "count": gated_merchant_count,
                    "percentage": round(100 * gated_merchant_count / self.doc_count, 2),
                },
            },
            "counters": percentages,
            "overlaps": overlap_percentages,
        }
    
    def log_summary(self, level: int = logging.INFO) -> None:
        """
        Log metrics summary as JSON.
        
        Args:
            level: Logging level (default: INFO)
        """
        summary = self.get_summary()
        logger.log(level, f"Address Metrics Summary: {json.dumps(summary, indent=2)}")
    
    def export_json(self, filepath: str) -> None:
        """
        Export metrics to JSON file.
        
        Args:
            filepath: Path to output JSON file
        """
        summary = self.get_summary()
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2)


# Global metrics instance (optional, for convenience)
_global_metrics: Optional[AddressMetrics] = None


def get_global_metrics() -> AddressMetrics:
    """Get or create global metrics instance."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = AddressMetrics()
    return _global_metrics


def reset_global_metrics() -> None:
    """Reset global metrics instance."""
    global _global_metrics
    _global_metrics = AddressMetrics()


# Convenience functions for global metrics
def record_address_features(
    address_profile: Dict[str, Any],
    merchant_address_consistency: Dict[str, Any],
    multi_address_profile: Dict[str, Any],
    merchant_confidence: float,
    doc_profile_confidence: float,
    doc_subtype: str,
) -> None:
    """
    Record all address features to global metrics.
    
    Convenience function for one-shot recording.
    
    Args:
        address_profile: Output from validate_address()
        merchant_address_consistency: Output from assess_merchant_address_consistency()
        multi_address_profile: Output from detect_multi_address_profile()
        merchant_confidence: Merchant extraction confidence
        doc_profile_confidence: Document confidence
        doc_subtype: Document subtype
    """
    metrics = get_global_metrics()
    
    metrics.record_address_profile(address_profile, doc_profile_confidence)
    metrics.record_multi_address(multi_address_profile, doc_profile_confidence)
    metrics.record_consistency(merchant_address_consistency, merchant_confidence, doc_profile_confidence)
    metrics.record_overlap(
        multi_address_profile.get("status", "UNKNOWN"),
        merchant_address_consistency.get("status", "UNKNOWN"),
        doc_subtype,
    )


if __name__ == "__main__":
    # Example usage
    print("Address Metrics - Example Usage\n")
    
    metrics = AddressMetrics()
    
    # Simulate 100 documents
    for i in range(100):
        # Mock features
        if i < 70:  # 70% have strong addresses
            address_profile = {
                "address_classification": "STRONG_ADDRESS",
                "address_score": 7,
                "address_type": "STANDARD",
            }
        elif i < 90:  # 20% have plausible addresses
            address_profile = {
                "address_classification": "PLAUSIBLE_ADDRESS",
                "address_score": 5,
                "address_type": "STANDARD",
            }
        else:  # 10% have weak addresses
            address_profile = {
                "address_classification": "WEAK_ADDRESS",
                "address_score": 2,
                "address_type": "PO_BOX",
            }
        
        if i < 30:  # 30% have multiple addresses
            multi_address_profile = {"status": "MULTIPLE", "count": 3}
        else:
            multi_address_profile = {"status": "SINGLE", "count": 1}
        
        if i < 20:  # 20% have mismatches
            consistency = {"status": "WEAK_MISMATCH", "score": 0.4}
        else:
            consistency = {"status": "CONSISTENT", "score": 0.9}
        
        metrics.record_address_profile(address_profile, 0.85)
        metrics.record_multi_address(multi_address_profile, 0.85)
        metrics.record_consistency(consistency, 0.8, 0.85)
        metrics.record_overlap(
            multi_address_profile["status"],
            consistency["status"],
            "INVOICE",
        )
    
    # Print summary
    summary = metrics.get_summary()
    print(json.dumps(summary, indent=2))
