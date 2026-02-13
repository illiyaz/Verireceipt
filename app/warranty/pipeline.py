"""
Main warranty claims analysis pipeline.

Orchestrates:
1. PDF extraction (text + images)
2. Duplicate detection
3. Fraud signal detection
4. Risk scoring and triage
"""

import time
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from .models import (
    WarrantyClaim, ClaimAnalysisResult, TriageClass,
    FraudSignal as FraudSignalModel, DuplicateMatch as DuplicateMatchModel
)
from .extractor import WarrantyClaimExtractor, ExtractedClaim
from .duplicates import DuplicateDetector, DuplicateMatch
from .signals import WarrantyFraudSignalDetector, FraudSignal, Severity
from .db import (
    save_claim, save_image_fingerprint, claim_exists,
    update_dealer_statistics
)


class WarrantyAnalysisPipeline:
    """
    Complete warranty claim analysis pipeline.
    """
    
    # Triage thresholds
    INVESTIGATE_THRESHOLD = 0.7  # Risk score >= 0.7 → INVESTIGATE
    REVIEW_THRESHOLD = 0.3      # Risk score >= 0.3 → REVIEW
    
    # Signal severity weights for risk scoring
    SEVERITY_WEIGHTS = {
        Severity.HIGH: 0.4,
        Severity.MEDIUM: 0.2,
        Severity.LOW: 0.1
    }
    
    def __init__(self):
        self.extractor = WarrantyClaimExtractor()
        self.duplicate_detector = DuplicateDetector()
        self.signal_detector = WarrantyFraudSignalDetector()
    
    def analyze(self, pdf_path: str, dealer_id: Optional[str] = None) -> ClaimAnalysisResult:
        """
        Analyze a warranty claim PDF.
        
        Args:
            pdf_path: Path to the warranty claim PDF
            dealer_id: Optional dealer ID for dealer-level checks
            
        Returns:
            ClaimAnalysisResult with complete analysis
        """
        start_time = time.time()
        
        # Stage 1: Extract data from PDF
        print(f"📄 Stage 1: Extracting data from PDF...")
        extracted = self.extractor.extract(pdf_path)
        
        claim_id = extracted.claim_id or self._generate_claim_id(pdf_path)
        
        # Check if claim already exists
        if claim_exists(claim_id):
            print(f"⚠️ Claim {claim_id} already exists in database")
        
        # Stage 2: Save images and compute hashes
        print(f"🖼️ Stage 2: Processing {len(extracted.images)} images...")
        image_data = []
        for idx, img in enumerate(extracted.images):
            if img.phash:
                save_image_fingerprint(
                    claim_id=claim_id,
                    image_index=idx,
                    phash=img.phash,
                    dhash=img.dhash,
                    file_hash=img.file_hash,
                    exif_data=img.exif,
                    dimensions=(img.width, img.height),
                    extraction_method=img.method,
                    page_number=img.page,
                    bbox=img.bbox
                )
                image_data.append({
                    "index": idx,
                    "phash": img.phash,
                    "dhash": img.dhash,
                    "file_hash": img.file_hash,
                    "size": img.size,  # Size in bytes for template filtering
                    "width": img.width,  # For aspect ratio detection
                    "height": img.height  # For aspect ratio detection
                })
        
        # Stage 3: Check for duplicates
        print(f"🔍 Stage 3: Checking for duplicates...")
        duplicates = self.duplicate_detector.check_duplicates(
            claim_id=claim_id,
            images=image_data,
            vin=extracted.vin,
            issue_description=extracted.issue_description,
            claim_date=extracted.claim_date
        )
        
        # Stage 4: Detect fraud signals
        print(f"🚨 Stage 4: Detecting fraud signals...")
        signals, warnings = self.signal_detector.detect_signals(
            claim_id=claim_id,
            parts_cost=extracted.parts_cost,
            labor_cost=extracted.labor_cost,
            tax=extracted.tax,
            total_amount=extracted.total_amount,
            brand=extracted.brand,
            model=extracted.model,
            year=extracted.year,
            issue_description=extracted.issue_description,
            claim_date=extracted.claim_date,
            decision_date=extracted.decision_date,
            status=extracted.status,
            dealer_id=dealer_id
        )
        
        # Add duplicate-based signals
        for dup in duplicates:
            if dup.match_type == "IMAGE_EXACT":
                signals.append(FraudSignal(
                    signal_type="DUPLICATE_IMAGE_EXACT",
                    severity=Severity.HIGH,
                    description=f"Exact duplicate image found in claim {dup.matched_claim_id}",
                    evidence={"matched_claim": dup.matched_claim_id}
                ))
            elif dup.match_type == "IMAGE_LIKELY_SAME":
                signals.append(FraudSignal(
                    signal_type="DUPLICATE_IMAGE_SIMILAR",
                    severity=Severity.HIGH,
                    description=f"Very similar image found in claim {dup.matched_claim_id} "
                               f"(similarity: {dup.similarity_score:.1%})",
                    evidence={
                        "matched_claim": dup.matched_claim_id,
                        "similarity": dup.similarity_score
                    }
                ))
            elif dup.match_type == "VIN_ISSUE_DUPLICATE":
                signals.append(FraudSignal(
                    signal_type="POTENTIAL_DUPLICATE_CLAIM",
                    severity=Severity.MEDIUM,
                    description=f"Similar claim found for same VIN: {dup.matched_claim_id}",
                    evidence={
                        "matched_claim": dup.matched_claim_id,
                        "similarity": dup.similarity_score
                    }
                ))
        
        # Stage 5: Calculate risk score
        print(f"📊 Stage 5: Calculating risk score...")
        risk_score = self._calculate_risk_score(signals, duplicates)
        
        # Stage 6: Determine triage class
        triage_class = self._determine_triage(risk_score, signals, duplicates)
        
        # Stage 7: Determine if suspicious
        is_suspicious = (
            risk_score >= self.REVIEW_THRESHOLD or
            len(duplicates) > 0 or
            any(s.severity == Severity.HIGH for s in signals)
        )
        
        # Stage 8: Generate summary
        summary = self._generate_summary(
            claim_id=claim_id,
            risk_score=risk_score,
            triage_class=triage_class,
            signals=signals,
            duplicates=duplicates
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        # Build result
        claim = WarrantyClaim(
            claim_id=claim_id,
            customer_name=extracted.customer_name,
            dealer_id=dealer_id,
            vin=extracted.vin,
            brand=extracted.brand,
            model=extracted.model,
            year=extracted.year,
            odometer=extracted.odometer,
            issue_description=extracted.issue_description,
            claim_date=extracted.claim_date,
            decision_date=extracted.decision_date,
            parts_cost=extracted.parts_cost,
            labor_cost=extracted.labor_cost,
            tax=extracted.tax,
            total_amount=extracted.total_amount,
            status=extracted.status,
            rejection_reason=extracted.rejection_reason,
            raw_text=extracted.raw_text
        )
        
        result = ClaimAnalysisResult(
            claim_id=claim_id,
            claim=claim,
            risk_score=risk_score,
            triage_class=triage_class,
            is_suspicious=is_suspicious,
            duplicates_found=[
                DuplicateMatchModel(
                    matched_claim_id=d.matched_claim_id,
                    match_type=d.match_type,
                    similarity_score=d.similarity_score,
                    details=d.details
                ) for d in duplicates
            ],
            fraud_signals=[
                FraudSignalModel(
                    signal_type=s.signal_type,
                    severity=s.severity.value,
                    description=s.description,
                    evidence=s.evidence
                ) for s in signals
            ],
            warnings=warnings,
            math_valid=not any(s.signal_type in ("TOTAL_MISMATCH", "NEGATIVE_TAX") for s in signals),
            date_valid=not any(s.signal_type.startswith("FUTURE_") or s.signal_type.startswith("DECISION_BEFORE") for s in signals),
            benchmark_valid=not any("BENCHMARK" in s.signal_type for s in signals),
            processing_time_ms=processing_time,
            extraction_method=extracted.images[0].method if extracted.images else "none",
            images_extracted=len(extracted.images),
            summary=summary
        )
        
        # Save to database
        self._save_result(result, pdf_path)
        
        # Update dealer statistics if dealer_id provided
        if dealer_id:
            update_dealer_statistics(dealer_id)
        
        print(f"✅ Analysis complete in {processing_time:.0f}ms")
        print(f"   Risk Score: {risk_score:.2f}")
        print(f"   Triage: {triage_class.value}")
        print(f"   Fraud Signals: {len(signals)}")
        print(f"   Duplicates: {len(duplicates)}")
        
        return result
    
    def _calculate_risk_score(
        self,
        signals: List[FraudSignal],
        duplicates: List[DuplicateMatch]
    ) -> float:
        """
        Calculate risk score from signals and duplicates.
        
        Score is 0.0 to 1.0, where:
        - 0.0 = No risk detected
        - 0.3 = Review threshold
        - 0.7 = Investigate threshold
        - 1.0 = Maximum risk
        """
        score = 0.0
        
        # Add signal contributions
        for signal in signals:
            weight = self.SEVERITY_WEIGHTS.get(signal.severity, 0.1)
            score += weight
        
        # Add duplicate contributions
        for dup in duplicates:
            if dup.match_type == "IMAGE_EXACT":
                score += 0.5
            elif dup.match_type == "IMAGE_LIKELY_SAME":
                score += 0.4
            elif dup.match_type == "IMAGE_SIMILAR":
                score += 0.2
            elif dup.match_type == "VIN_ISSUE_DUPLICATE":
                score += 0.3
        
        # Cap at 1.0
        return min(score, 1.0)
    
    def _determine_triage(
        self,
        risk_score: float,
        signals: List[FraudSignal],
        duplicates: List[DuplicateMatch]
    ) -> TriageClass:
        """Determine triage classification."""
        # Immediate investigation triggers
        if any(d.match_type == "IMAGE_EXACT" for d in duplicates):
            return TriageClass.INVESTIGATE
        
        if any(s.severity == Severity.HIGH and s.signal_type in (
            "NEGATIVE_TAX", "FUTURE_CLAIM_DATE", "CLAIM_BEFORE_MANUFACTURE",
            "DECISION_BEFORE_CLAIM", "HIGH_RISK_DEALER"
        ) for s in signals):
            return TriageClass.INVESTIGATE
        
        # Score-based triage
        if risk_score >= self.INVESTIGATE_THRESHOLD:
            return TriageClass.INVESTIGATE
        elif risk_score >= self.REVIEW_THRESHOLD:
            return TriageClass.REVIEW
        else:
            return TriageClass.AUTO_APPROVE
    
    def _generate_summary(
        self,
        claim_id: str,
        risk_score: float,
        triage_class: TriageClass,
        signals: List[FraudSignal],
        duplicates: List[DuplicateMatch]
    ) -> str:
        """Generate human-readable summary."""
        parts = [f"Claim {claim_id}:"]
        
        if triage_class == TriageClass.AUTO_APPROVE:
            parts.append("No significant issues detected. Recommend auto-approval.")
        elif triage_class == TriageClass.REVIEW:
            parts.append(f"Moderate risk detected (score: {risk_score:.2f}). Manual review recommended.")
        else:
            parts.append(f"HIGH RISK (score: {risk_score:.2f}). Investigation required.")
        
        if duplicates:
            exact = sum(1 for d in duplicates if d.match_type == "IMAGE_EXACT")
            similar = sum(1 for d in duplicates if "SIMILAR" in d.match_type or "LIKELY" in d.match_type)
            
            if exact:
                parts.append(f"⚠️ {exact} exact duplicate image(s) found!")
            if similar:
                parts.append(f"⚠️ {similar} similar image(s) found.")
        
        high_signals = [s for s in signals if s.severity == Severity.HIGH]
        if high_signals:
            parts.append(f"Critical issues: {', '.join(s.signal_type for s in high_signals)}")
        
        return " ".join(parts)
    
    def _save_result(self, result: ClaimAnalysisResult, pdf_path: str):
        """Save analysis result to database."""
        claim_data = {
            "claim_id": result.claim_id,
            "customer_name": result.claim.customer_name,
            "dealer_id": result.claim.dealer_id,
            "dealer_name": result.claim.dealer_name,
            "vin": result.claim.vin,
            "brand": result.claim.brand,
            "model": result.claim.model,
            "year": result.claim.year,
            "odometer": result.claim.odometer,
            "issue_description": result.claim.issue_description,
            "claim_date": result.claim.claim_date,
            "decision_date": result.claim.decision_date,
            "parts_cost": result.claim.parts_cost,
            "labor_cost": result.claim.labor_cost,
            "tax": result.claim.tax,
            "total_amount": result.claim.total_amount,
            "status": result.claim.status.value if result.claim.status else None,
            "rejection_reason": result.claim.rejection_reason,
            "risk_score": result.risk_score,
            "triage_class": result.triage_class.value,
            "fraud_signals": [s.dict() for s in result.fraud_signals],
            "warnings": result.warnings,
            "is_suspicious": result.is_suspicious,
            "pdf_path": pdf_path,
            "raw_text": result.claim.raw_text
        }
        
        save_claim(claim_data)
    
    def _generate_claim_id(self, pdf_path: str) -> str:
        """Generate a claim ID from PDF path if not found in document."""
        import hashlib
        import os
        
        filename = os.path.basename(pdf_path)
        name_without_ext = os.path.splitext(filename)[0]
        
        # If filename looks like a claim ID (6 alphanumeric chars), use it
        if len(name_without_ext) == 6 and name_without_ext.isalnum():
            return name_without_ext.upper()
        
        # Otherwise generate from hash
        hash_val = hashlib.md5(pdf_path.encode()).hexdigest()[:6].upper()
        return f"GEN{hash_val}"


def analyze_warranty_claim(
    pdf_path: str,
    dealer_id: Optional[str] = None
) -> ClaimAnalysisResult:
    """
    Convenience function to analyze a warranty claim.
    
    Args:
        pdf_path: Path to the warranty claim PDF
        dealer_id: Optional dealer ID
        
    Returns:
        ClaimAnalysisResult with complete analysis
    """
    pipeline = WarrantyAnalysisPipeline()
    return pipeline.analyze(pdf_path, dealer_id)
