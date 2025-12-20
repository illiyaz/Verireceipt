"""
Feedback data models for local learning system.

Stores user corrections and feedback to improve fraud detection accuracy.
All data stays local - GDPR compliant by design.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class FeedbackType(str, Enum):
    """Type of feedback provided by user."""
    VERDICT_CORRECTION = "verdict_correction"  # User corrected the verdict
    FALSE_POSITIVE = "false_positive"  # System said fake, was real
    FALSE_NEGATIVE = "false_negative"  # System said real, was fake
    CONFIDENCE_ISSUE = "confidence_issue"  # Confidence was wrong
    FEATURE_REQUEST = "feature_request"  # User wants new detection


class CorrectVerdict(str, Enum):
    """Correct verdict as determined by user."""
    REAL = "real"
    FAKE = "fake"
    SUSPICIOUS = "suspicious"
    UNCERTAIN = "uncertain"


class ReceiptFeedback(BaseModel):
    """
    User feedback on a receipt analysis.
    
    Stored locally to improve system accuracy over time.
    """
    # Identifiers
    feedback_id: str = Field(description="Unique feedback ID")
    receipt_id: Optional[str] = Field(None, description="Receipt identifier (if available)")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Original Analysis
    system_verdict: str = Field(description="What the system said (real/fake/suspicious)")
    system_confidence: float = Field(description="System confidence (0.0-1.0)")
    system_reasoning: List[str] = Field(default_factory=list, description="System's reasoning")
    
    # User Correction
    correct_verdict: CorrectVerdict = Field(description="User's correct verdict")
    feedback_type: FeedbackType = Field(description="Type of feedback")
    user_notes: Optional[str] = Field(None, description="User's explanation")
    
    # Analysis Context
    engines_used: List[str] = Field(default_factory=list, description="Which engines ran")
    rule_based_score: Optional[float] = Field(None, description="Rule-based score")
    vision_llm_verdict: Optional[str] = Field(None, description="Vision LLM verdict")
    
    # Fraud Indicators
    detected_indicators: List[str] = Field(default_factory=list, description="Fraud indicators found")
    missed_indicators: List[str] = Field(default_factory=list, description="Indicators user says were missed")
    false_indicators: List[str] = Field(default_factory=list, description="Indicators that were wrong")
    
    # Learning Data (anonymized)
    merchant_pattern: Optional[str] = Field(None, description="Merchant name pattern (anonymized)")
    software_detected: Optional[str] = Field(None, description="PDF software detected")
    has_date_issue: bool = Field(False, description="Date manipulation detected")
    has_spacing_issue: bool = Field(False, description="Spacing anomaly detected")
    
    # Metadata
    user_id: Optional[str] = Field(None, description="User who provided feedback")
    session_id: Optional[str] = Field(None, description="Analysis session ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "feedback_id": "fb_123456",
                "system_verdict": "suspicious",
                "system_confidence": 0.70,
                "correct_verdict": "fake",
                "feedback_type": "false_negative",
                "user_notes": "This is clearly fake - iLovePDF watermark visible",
                "detected_indicators": ["Suspicious Software: iLovePDF"],
                "missed_indicators": ["Spacing anomalies in total amount"]
            }
        }


class FeedbackStats(BaseModel):
    """Statistics on feedback and system accuracy."""
    total_feedback: int = 0
    correct_verdicts: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    accuracy: float = 0.0
    
    # By verdict type
    real_receipts: int = 0
    fake_receipts: int = 0
    suspicious_receipts: int = 0
    
    # Common issues
    most_common_missed_indicators: List[Dict[str, Any]] = Field(default_factory=list)
    most_common_false_indicators: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Time period
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class LearningRule(BaseModel):
    """
    A learned rule from user feedback.
    
    These are patterns discovered from corrections that improve detection.
    """
    rule_id: str = Field(description="Unique rule ID")
    rule_type: str = Field(description="Type of rule (merchant, software, pattern, etc.)")
    pattern: str = Field(description="Pattern to match")
    action: str = Field(description="Action to take (flag_suspicious, increase_score, etc.)")
    confidence_adjustment: float = Field(0.0, description="How much to adjust confidence")
    
    # Learning metadata
    learned_from_feedback_count: int = Field(1, description="How many feedbacks contributed")
    accuracy_on_validation: float = Field(0.0, description="Accuracy when tested")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    # Status
    enabled: bool = Field(True, description="Whether rule is active")
    auto_learned: bool = Field(True, description="Was this learned automatically?")
    
    class Config:
        json_schema_extra = {
            "example": {
                "rule_id": "lr_001",
                "rule_type": "suspicious_software",
                "pattern": "PDFCreator",
                "action": "flag_suspicious",
                "confidence_adjustment": 0.15,
                "learned_from_feedback_count": 5,
                "accuracy_on_validation": 0.92
            }
        }


class FeedbackSubmission(BaseModel):
    """Request model for submitting feedback."""
    receipt_id: Optional[str] = None
    correct_verdict: CorrectVerdict
    user_notes: Optional[str] = None
    missed_indicators: List[str] = Field(default_factory=list)
    false_indicators: List[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""
    success: bool
    feedback_id: str
    message: str
    rules_updated: int = 0
    new_patterns_learned: List[str] = Field(default_factory=list)
