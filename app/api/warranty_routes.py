"""
API routes for warranty claims analysis.

Endpoints:
- POST /warranty/analyze - Analyze a warranty claim PDF
- GET /warranty/claim/{claim_id} - Get claim details
- POST /warranty/feedback - Submit adjuster feedback
- GET /warranty/duplicates/{claim_id} - Get duplicate matches for a claim
"""

import os
import tempfile
import shutil
from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel

from ..warranty.pipeline import analyze_warranty_claim
from ..warranty.db import get_claim, save_feedback, get_duplicates_for_claim
from ..warranty.models import FeedbackVerdict


router = APIRouter(prefix="/warranty", tags=["warranty"])


class FeedbackRequest(BaseModel):
    claim_id: str
    verdict: FeedbackVerdict
    adjuster_id: Optional[str] = None
    notes: Optional[str] = None


class AnalyzeResponse(BaseModel):
    claim_id: str
    risk_score: float
    triage_class: str
    is_suspicious: bool
    fraud_signals: list
    warnings: list
    duplicates_found: list
    summary: str
    processing_time_ms: float
    images_extracted: int
    
    # Extracted data
    customer_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    vin: Optional[str] = None
    issue_description: Optional[str] = None
    claim_date: Optional[str] = None
    parts_cost: Optional[float] = None
    labor_cost: Optional[float] = None
    tax: Optional[float] = None
    total_amount: Optional[float] = None
    status: Optional[str] = None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_warranty(
    file: UploadFile = File(...),
    dealer_id: Optional[str] = Form(None)
):
    """
    Analyze a warranty claim PDF for fraud detection.
    
    Uploads a PDF file and returns:
    - Risk score (0.0 - 1.0)
    - Triage classification (AUTO_APPROVE, REVIEW, INVESTIGATE)
    - Fraud signals detected
    - Duplicate image/claim matches
    - Extracted claim data
    """
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )
    
    # Save uploaded file temporarily
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Run analysis pipeline
        result = analyze_warranty_claim(temp_path, dealer_id=dealer_id)
        
        # Build response
        return AnalyzeResponse(
            claim_id=result.claim_id,
            risk_score=result.risk_score,
            triage_class=result.triage_class.value,
            is_suspicious=result.is_suspicious,
            fraud_signals=[s.dict() for s in result.fraud_signals],
            warnings=result.warnings,
            duplicates_found=[d.dict() for d in result.duplicates_found],
            summary=result.summary,
            processing_time_ms=result.processing_time_ms,
            images_extracted=result.images_extracted,
            customer_name=result.claim.customer_name,
            brand=result.claim.brand,
            model=result.claim.model,
            year=result.claim.year,
            vin=result.claim.vin,
            issue_description=result.claim.issue_description,
            claim_date=result.claim.claim_date,
            parts_cost=result.claim.parts_cost,
            labor_cost=result.claim.labor_cost,
            tax=result.claim.tax,
            total_amount=result.claim.total_amount,
            status=result.claim.status.value if result.claim.status else None
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )
    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.get("/claim/{claim_id}")
async def get_claim_details(claim_id: str):
    """
    Get details of a previously analyzed claim.
    """
    claim = get_claim(claim_id)
    
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {claim_id} not found"
        )
    
    return claim


@router.get("/duplicates/{claim_id}")
async def get_claim_duplicates(claim_id: str):
    """
    Get all duplicate matches for a claim.
    """
    claim = get_claim(claim_id)
    
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {claim_id} not found"
        )
    
    duplicates = get_duplicates_for_claim(claim_id)
    
    return {
        "claim_id": claim_id,
        "duplicates": duplicates
    }


@router.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """
    Submit adjuster feedback on a claim analysis.
    
    Used to improve the ML model over time.
    """
    # Verify claim exists
    claim = get_claim(feedback.claim_id)
    
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {feedback.claim_id} not found"
        )
    
    # Save feedback
    feedback_id = save_feedback(
        claim_id=feedback.claim_id,
        verdict=feedback.verdict.value,
        adjuster_id=feedback.adjuster_id,
        notes=feedback.notes
    )
    
    return {
        "status": "success",
        "feedback_id": feedback_id,
        "message": f"Feedback recorded for claim {feedback.claim_id}"
    }


@router.get("/stats")
async def get_warranty_stats():
    """
    Get overall warranty claim statistics.
    """
    from ..warranty.db import get_connection, release_connection, _get_cursor
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        
        # Total claims
        cursor.execute("SELECT COUNT(*) as cnt FROM warranty_claims")
        row = cursor.fetchone()
        total_claims = row["cnt"] if isinstance(row, dict) else row[0]
        
        # By triage class
        cursor.execute("""
            SELECT triage_class, COUNT(*) as cnt
            FROM warranty_claims 
            GROUP BY triage_class
        """)
        by_triage = {}
        for row in cursor.fetchall():
            if isinstance(row, dict):
                by_triage[row["triage_class"]] = row["cnt"]
            else:
                by_triage[row[0]] = row[1]
        
        # Suspicious count
        cursor.execute("SELECT COUNT(*) as cnt FROM warranty_claims WHERE is_suspicious = 1")
        row = cursor.fetchone()
        suspicious_count = row["cnt"] if isinstance(row, dict) else row[0]
        
        # Duplicate count
        cursor.execute("SELECT COUNT(DISTINCT claim_id_1) as cnt FROM warranty_duplicate_matches")
        row = cursor.fetchone()
        claims_with_duplicates = row["cnt"] if isinstance(row, dict) else row[0]
        
        # Feedback summary
        cursor.execute("""
            SELECT verdict, COUNT(*) as cnt
            FROM warranty_feedback 
            GROUP BY verdict
        """)
        feedback_summary = {}
        for row in cursor.fetchall():
            if isinstance(row, dict):
                feedback_summary[row["verdict"]] = row["cnt"]
            else:
                feedback_summary[row[0]] = row[1]
        
        return {
            "total_claims": total_claims,
            "by_triage": by_triage,
            "suspicious_count": suspicious_count,
            "claims_with_duplicates": claims_with_duplicates,
            "feedback_summary": feedback_summary
        }
    finally:
        release_connection(conn)
