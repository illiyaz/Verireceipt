"""
Feedback API endpoints for local learning system.

Allows users to correct verdicts and improve system accuracy.
All data stays local - privacy-first design.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime, timezone
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

# NEW: Import LabelV1 schema
from app.schemas.labels import DocumentLabelV1, AnnotatorJudgment
from pathlib import Path
import json


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(
    submission: FeedbackSubmission,
    session_id: Optional[str] = None
):
    """
    LEGACY: Submit user feedback on a receipt analysis.
    
    Use /submit/structured for new ML-ready labels.
    This endpoint is kept for backward compatibility.
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
        # Build user_notes with all review sections
        notes_parts = []
        if submission.user_notes:
            notes_parts.append(submission.user_notes)
        if submission.font_manipulation:
            notes_parts.append("[FONT_MANIPULATION_DETECTED]")
        if submission.address_issues:
            notes_parts.append(f"[ADDRESS] {submission.address_issues}")
        if submission.visual_integrity_issues:
            notes_parts.append(f"[VISUAL] {submission.visual_integrity_issues}")
        if submission.amount_verification_notes:
            notes_parts.append(f"[AMOUNT] {submission.amount_verification_notes}")
        combined_notes = " | ".join(notes_parts) if notes_parts else None

        feedback = ReceiptFeedback(
            feedback_id=feedback_id,
            receipt_id=submission.receipt_id,
            system_verdict="unknown",  # Would come from session
            system_confidence=0.0,  # Would come from session
            correct_verdict=submission.correct_verdict,
            feedback_type=feedback_type,
            user_notes=combined_notes,
            missed_indicators=submission.missed_indicators,
            false_indicators=submission.false_indicators,
            confirmed_indicators=submission.confirmed_indicators,
            data_corrections=submission.data_corrections,
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


@router.post("/submit/structured", response_model=FeedbackResponse)
async def submit_structured_feedback(
    doc_id: str,
    judgment: AnnotatorJudgment,
    session_id: Optional[str] = None
):
    """
    NEW: Submit structured feedback using LabelV1 schema.
    
    This endpoint produces ML-ready labels with:
    - Structured fraud types and decision reasons
    - Evidence strength assessment
    - Signal reviews
    - Field-level validation
    
    Args:
        doc_id: Document identifier
        judgment: Structured annotator judgment
        session_id: Optional session ID
    
    Returns:
        Feedback response with validation results
    """
    try:
        # Create DocumentLabelV1
        label = DocumentLabelV1(
            label_version="v1",
            doc_id=doc_id,
            source_batch="api_structured",
            created_at=datetime.now(timezone.utc),
            tool_version="api_v1.0",
            annotator_judgments=[judgment],
            metadata={
                "session_id": session_id,
                "submitted_via": "api"
            }
        )
        
        # Save to JSONL
        labels_file = Path("data/labels/v1/labels.jsonl")
        labels_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(labels_file, 'a') as f:
            f.write(label.model_dump_json() + '\n')
        
        # Also save to legacy feedback store for compatibility
        from app.ml.feedback_adapter import FeedbackToLabelAdapter
        adapter = FeedbackToLabelAdapter()
        
        # Convert back to legacy format for learning system
        legacy_verdict_map = {
            "GENUINE": CorrectVerdict.REAL,
            "FRAUDULENT": CorrectVerdict.FAKE,
            "INCONCLUSIVE": CorrectVerdict.SUSPICIOUS
        }
        
        legacy_feedback = ReceiptFeedback(
            feedback_id=f"fb_{uuid.uuid4().hex[:12]}",
            receipt_id=doc_id,
            system_verdict="unknown",
            system_confidence=0.0,
            correct_verdict=legacy_verdict_map.get(judgment.doc_outcome, CorrectVerdict.UNCERTAIN),
            feedback_type=FeedbackType.VERDICT_CORRECTION,
            user_notes=judgment.notes,
            missed_indicators=judgment.decision_reasons if judgment.doc_outcome == "FRAUDULENT" else [],
            session_id=session_id
        )
        
        store = get_feedback_store()
        store.save_feedback(legacy_feedback)
        
        return FeedbackResponse(
            success=True,
            feedback_id=label.doc_id,
            message="Structured feedback saved successfully! Ready for ML training.",
            rules_updated=0,
            new_patterns_learned=[]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save structured feedback: {str(e)}")


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
