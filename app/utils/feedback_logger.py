"""
Feedback logging utilities for VeriReceipt.

Handles logging human feedback to CSV for later ML training.
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Optional


FEEDBACK_LOG_FILE = Path("data/logs/feedback.csv")
FEEDBACK_HEADERS = [
    "timestamp",
    "analysis_ref",
    "receipt_ref",
    "engine_label",
    "engine_score",
    "given_label",
    "reviewer_id",
    "comment",
    "reason_code",
]


def ensure_feedback_log_exists():
    """Create feedback CSV with headers if it doesn't exist."""
    FEEDBACK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if not FEEDBACK_LOG_FILE.exists():
        with open(FEEDBACK_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FEEDBACK_HEADERS)
            writer.writeheader()


def log_feedback(
    analysis_ref: str,
    given_label: str,
    engine_label: Optional[str] = None,
    engine_score: Optional[float] = None,
    receipt_ref: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    comment: Optional[str] = None,
    reason_code: Optional[str] = None,
) -> str:
    """
    Log human feedback to CSV.
    
    Args:
        analysis_ref: Reference to the original analysis (filename or ID)
        given_label: Human-corrected label (real/suspicious/fake)
        engine_label: Original engine prediction
        engine_score: Original engine score
        receipt_ref: Receipt identifier
        reviewer_id: Who provided the feedback
        comment: Free-text comment
        reason_code: Structured reason code
    
    Returns:
        Timestamp of the logged feedback
    """
    ensure_feedback_log_exists()
    
    timestamp = datetime.now().isoformat()
    
    row = {
        "timestamp": timestamp,
        "analysis_ref": analysis_ref,
        "receipt_ref": receipt_ref or "",
        "engine_label": engine_label or "",
        "engine_score": engine_score if engine_score is not None else "",
        "given_label": given_label,
        "reviewer_id": reviewer_id or "",
        "comment": comment or "",
        "reason_code": reason_code or "",
    }
    
    with open(FEEDBACK_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FEEDBACK_HEADERS)
        writer.writerow(row)
    
    return timestamp
