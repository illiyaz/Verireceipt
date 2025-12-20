"""
Feedback API endpoints for local learning system.

Allows users to correct verdicts and improve system accuracy.
All data stays local - privacy-first design.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime
import uuid

from app.models.feedback import (
    ReceiptFeedback,
    FeedbackSubmission,
    FeedbackResponse,
    FeedbackStats,
    LearningRule,
    FeedbackType,
    CorrectVerdict
)
from app.repository.feedback_store import get_feedback_store
from app.pipelines.learning import learn_from_feedback


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(
    submission: FeedbackSubmission,
    session_id: Optional[str] = None
):
    """
    Submit user feedback on a receipt analysis.
    
    This is the primary endpoint for collecting corrections.
    The system learns from this feedback to improve accuracy.
    """
    try:
        store = get_feedback_store()
        
        # Get the original analysis from session (if available)
        # For now, we'll create a basic feedback entry
        # In production, you'd retrieve the full analysis from session storage
        
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
        
        # Determine feedback type
        feedback_type = FeedbackType.VERDICT_CORRECTION
        
        # Create feedback object
        feedback = ReceiptFeedback(
            feedback_id=feedback_id,
            receipt_id=submission.receipt_id,
            system_verdict="unknown",  # Would come from session
            system_confidence=0.0,  # Would come from session
            correct_verdict=submission.correct_verdict,
            feedback_type=feedback_type,
            user_notes=submission.user_notes,
            missed_indicators=submission.missed_indicators,
            false_indicators=submission.false_indicators,
            session_id=session_id
        )
        
        # Save feedback
        store.save_feedback(feedback)
        
        # Learn from feedback
        rules_updated, new_patterns = learn_from_feedback(feedback)
        
        return FeedbackResponse(
            success=True,
            feedback_id=feedback_id,
            message="Thank you for your feedback! The system will learn from this correction.",
            rules_updated=rules_updated,
            new_patterns_learned=new_patterns
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save feedback: {str(e)}")


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats(days: int = 30):
    """
    Get feedback statistics and accuracy metrics.
    
    Shows how well the system is performing based on user corrections.
    """
    try:
        store = get_feedback_store()
        return store.get_stats(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/history", response_model=List[ReceiptFeedback])
async def get_feedback_history(limit: int = 50, offset: int = 0):
    """
    Get feedback history.
    
    Shows all user corrections for review and analysis.
    """
    try:
        store = get_feedback_store()
        return store.get_all_feedback(limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.get("/learned-rules", response_model=List[LearningRule])
async def get_learned_rules(enabled_only: bool = True):
    """
    Get all learned rules.
    
    Shows patterns the system has learned from user feedback.
    """
    try:
        store = get_feedback_store()
        return store.get_learned_rules(enabled_only=enabled_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get rules: {str(e)}")


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, enabled: bool):
    """
    Enable or disable a learned rule.
    
    Allows manual control over which learned patterns are active.
    """
    try:
        store = get_feedback_store()
        
        # Get rule
        rules = store.get_learned_rules(enabled_only=False)
        rule = next((r for r in rules if r.rule_id == rule_id), None)
        
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        
        # Update rule
        rule.enabled = enabled
        rule.last_updated = datetime.utcnow()
        store.save_learned_rule(rule)
        
        return {"success": True, "rule_id": rule_id, "enabled": enabled}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle rule: {str(e)}")


@router.get("/export")
async def export_learned_rules():
    """
    Export learned rules as JSON.
    
    Allows backing up or sharing learned patterns.
    """
    try:
        store = get_feedback_store()
        rules = store.get_learned_rules(enabled_only=False)
        
        return {
            "exported_at": datetime.utcnow().isoformat(),
            "rule_count": len(rules),
            "rules": [rule.dict() for rule in rules]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export rules: {str(e)}")


@router.post("/import")
async def import_learned_rules(rules_data: dict):
    """
    Import learned rules from JSON.
    
    Allows restoring or sharing learned patterns.
    """
    try:
        store = get_feedback_store()
        
        rules = rules_data.get("rules", [])
        imported_count = 0
        
        for rule_dict in rules:
            try:
                rule = LearningRule(**rule_dict)
                store.save_learned_rule(rule)
                imported_count += 1
            except Exception as e:
                print(f"Failed to import rule: {e}")
                continue
        
        return {
            "success": True,
            "imported_count": imported_count,
            "total_rules": len(rules)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import rules: {str(e)}")
