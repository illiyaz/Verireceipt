"""
Pydantic models for warranty claims processing.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import date, datetime
from enum import Enum


class ClaimStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class TriageClass(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    REVIEW = "REVIEW"
    INVESTIGATE = "INVESTIGATE"


class FeedbackVerdict(str, Enum):
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    VALID_CLAIM = "VALID_CLAIM"


class ExtractedImage(BaseModel):
    """Image extracted from a warranty claim PDF."""
    model_config = {"extra": "allow"}
    
    data: bytes
    page: int
    index: int
    method: str  # "embedded" or "render_crop"
    bbox: Optional[tuple] = None
    phash: Optional[str] = None
    dhash: Optional[str] = None
    file_hash: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = None  # File size in bytes
    exif: Optional[Dict[str, Any]] = None  # EXIF metadata dict
    exif_timestamp: Optional[str] = None
    exif_gps_lat: Optional[float] = None
    exif_gps_lon: Optional[float] = None
    exif_device: Optional[str] = None


class WarrantyClaim(BaseModel):
    """Structured warranty claim data extracted from PDF."""
    claim_id: str
    customer_name: Optional[str] = None
    dealer_id: Optional[str] = None
    dealer_name: Optional[str] = None
    
    # Vehicle info
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    odometer: Optional[int] = None
    
    # Claim details
    issue_description: Optional[str] = None
    claim_date: Optional[str] = None
    decision_date: Optional[str] = None
    
    # Amounts
    parts_cost: Optional[float] = None
    labor_cost: Optional[float] = None
    tax: Optional[float] = None
    total_amount: Optional[float] = None
    
    # Status
    status: Optional[ClaimStatus] = None
    rejection_reason: Optional[str] = None
    
    # Extracted images
    images: List[ExtractedImage] = Field(default_factory=list)
    
    # Raw text for ML features
    raw_text: Optional[str] = None


class DuplicateMatch(BaseModel):
    """A detected duplicate match."""
    matched_claim_id: str
    match_type: str  # IMAGE_EXACT, IMAGE_SIMILAR, CLAIM_DUPLICATE
    similarity_score: float
    matched_image_index: Optional[int] = None
    details: Optional[str] = None


class FraudSignal(BaseModel):
    """A detected fraud signal."""
    signal_type: str
    severity: str  # HIGH, MEDIUM, LOW
    description: str
    evidence: Optional[Dict[str, Any]] = None


class ClaimAnalysisResult(BaseModel):
    """Complete analysis result for a warranty claim."""
    claim_id: str
    claim: WarrantyClaim
    
    # Risk assessment
    risk_score: float = Field(ge=0.0, le=1.0)
    triage_class: TriageClass
    is_suspicious: bool
    
    # Duplicate detection
    duplicates_found: List[DuplicateMatch] = Field(default_factory=list)
    
    # Fraud signals
    fraud_signals: List[FraudSignal] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    # Validation results
    math_valid: bool = True
    date_valid: bool = True
    benchmark_valid: bool = True
    
    # Processing metadata
    processing_time_ms: Optional[float] = None
    extraction_method: Optional[str] = None
    images_extracted: int = 0
    
    # Explanation
    summary: Optional[str] = None


class WarrantyFeedback(BaseModel):
    """Feedback from adjuster on a claim analysis."""
    claim_id: str
    adjuster_id: Optional[str] = None
    verdict: FeedbackVerdict
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
