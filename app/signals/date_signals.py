"""
Date signal wrappers for Unified Signal Contract (V1).

Signals:
- date.missing: Expected date is missing
- date.future: Date is in the future
- date.gap_suspicious: Date gap between issue and due dates is suspicious
"""

from typing import Dict, Any, Optional
from datetime import datetime, date
from app.schemas.receipt import SignalV1


def signal_date_missing(
    date_value: Optional[str],
    doc_subtype: str,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert missing date to unified signal.
    
    Signal: date.missing
    Purpose: Indicates expected date is missing
    
    Args:
        date_value: Extracted date value
        doc_subtype: Document subtype
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="date.missing",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Date validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # Only trigger for transactional documents
    transactional_types = {"INVOICE", "TAX_INVOICE", "VAT_INVOICE", "POS_RECEIPT", "CREDIT_NOTE"}
    if doc_subtype not in transactional_types:
        return SignalV1(
            name="date.missing",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={"doc_subtype": doc_subtype},
            interpretation=f"Date not required for {doc_subtype}",
        )
    
    if not date_value:
        return SignalV1(
            name="date.missing",
            status="TRIGGERED",
            confidence=0.7,
            evidence={
                "doc_subtype": doc_subtype,
                "doc_profile_confidence": doc_profile_confidence,
            },
            interpretation=f"Missing date in {doc_subtype}",
        )
    
    return SignalV1(
        name="date.missing",
        status="NOT_TRIGGERED",
        confidence=0.9,
        evidence={"date_present": True},
        interpretation="Date present",
    )


def signal_date_future(
    date_value: Optional[str],
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert future date to unified signal.
    
    Signal: date.future
    Purpose: Indicates date is in the future
    
    Args:
        date_value: Extracted date value (ISO format)
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="date.future",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Date validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    if not date_value:
        return SignalV1(
            name="date.future",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={},
            interpretation="No date to validate",
        )
    
    try:
        # Parse date
        if isinstance(date_value, str):
            parsed_date = datetime.fromisoformat(date_value.replace("Z", "+00:00")).date()
        elif isinstance(date_value, (datetime, date)):
            parsed_date = date_value if isinstance(date_value, date) else date_value.date()
        else:
            raise ValueError(f"Invalid date type: {type(date_value)}")
        
        today = datetime.now().date()
        days_in_future = (parsed_date - today).days
        
        # Trigger if date is more than 1 day in the future (allow for timezone differences)
        if days_in_future > 1:
            return SignalV1(
                name="date.future",
                status="TRIGGERED",
                confidence=0.8,
                evidence={
                    "days_in_future": days_in_future,
                    "date_year": parsed_date.year,
                    "date_month": parsed_date.month,
                },
                interpretation=f"Date is {days_in_future} days in the future",
            )
        
        return SignalV1(
            name="date.future",
            status="NOT_TRIGGERED",
            confidence=0.9,
            evidence={
                "days_in_future": days_in_future,
            },
            interpretation="Date is not in the future",
        )
    
    except Exception as e:
        return SignalV1(
            name="date.future",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={"error": "date_parse_failed"},
            interpretation=f"Could not parse date: {str(e)[:50]}",
        )


def signal_date_gap_suspicious(
    issue_date: Optional[str],
    due_date: Optional[str],
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert suspicious date gap to unified signal.
    
    Signal: date.gap_suspicious
    Purpose: Indicates suspicious gap between issue and due dates
    
    Args:
        issue_date: Issue date (ISO format)
        due_date: Due date (ISO format)
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="date.gap_suspicious",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Date gap validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    if not issue_date or not due_date:
        return SignalV1(
            name="date.gap_suspicious",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={
                "issue_date_present": bool(issue_date),
                "due_date_present": bool(due_date),
            },
            interpretation="Insufficient dates for gap analysis",
        )
    
    try:
        # Parse dates
        if isinstance(issue_date, str):
            parsed_issue = datetime.fromisoformat(issue_date.replace("Z", "+00:00")).date()
        else:
            parsed_issue = issue_date if isinstance(issue_date, date) else issue_date.date()
        
        if isinstance(due_date, str):
            parsed_due = datetime.fromisoformat(due_date.replace("Z", "+00:00")).date()
        else:
            parsed_due = due_date if isinstance(due_date, date) else due_date.date()
        
        gap_days = (parsed_due - parsed_issue).days
        
        # Suspicious if:
        # - Due date is before issue date (negative gap)
        # - Gap is extremely long (> 365 days)
        # - Gap is extremely short for invoices (< 1 day)
        
        if gap_days < 0:
            return SignalV1(
                name="date.gap_suspicious",
                status="TRIGGERED",
                confidence=0.9,
                evidence={
                    "gap_days": gap_days,
                    "anomaly": "due_before_issue",
                },
                interpretation=f"Due date is {abs(gap_days)} days before issue date",
            )
        
        if gap_days > 365:
            return SignalV1(
                name="date.gap_suspicious",
                status="TRIGGERED",
                confidence=0.7,
                evidence={
                    "gap_days": gap_days,
                    "anomaly": "gap_too_long",
                },
                interpretation=f"Date gap is unusually long: {gap_days} days",
            )
        
        return SignalV1(
            name="date.gap_suspicious",
            status="NOT_TRIGGERED",
            confidence=0.8,
            evidence={
                "gap_days": gap_days,
            },
            interpretation=f"Date gap is normal: {gap_days} days",
        )
    
    except Exception as e:
        return SignalV1(
            name="date.gap_suspicious",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={"error": "date_parse_failed"},
            interpretation=f"Could not parse dates: {str(e)[:50]}",
        )
