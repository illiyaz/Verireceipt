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
import traceback
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Persistent storage for uploaded warranty PDFs
WARRANTY_PDF_DIR = Path(os.getenv("WARRANTY_PDF_DIR", "data/warranty_pdfs"))
WARRANTY_PDF_DIR.mkdir(parents=True, exist_ok=True)

from ..warranty.pipeline import analyze_warranty_claim
from ..warranty.db import get_claim, save_feedback, get_duplicates_for_claim, get_duplicate_audit
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
        
        # Normalize dealer_id: empty string → None
        effective_dealer_id = dealer_id.strip() if dealer_id else None
        if effective_dealer_id == "":
            effective_dealer_id = None
        
        # Run analysis pipeline
        result = analyze_warranty_claim(temp_path, dealer_id=effective_dealer_id)
        
        # Persist the PDF so auditors can view it later
        try:
            persist_path = WARRANTY_PDF_DIR / f"{result.claim_id}.pdf"
            shutil.copy2(temp_path, str(persist_path))
        except Exception as copy_err:
            print(f"\u26a0\ufe0f Could not persist PDF: {copy_err}")
        
        # Build response
        return AnalyzeResponse(
            claim_id=result.claim_id,
            risk_score=result.risk_score,
            triage_class=result.triage_class.value,
            is_suspicious=result.is_suspicious,
            fraud_signals=[s.model_dump() if hasattr(s, 'model_dump') else s.dict() for s in result.fraud_signals],
            warnings=result.warnings,
            duplicates_found=[d.model_dump() if hasattr(d, 'model_dump') else d.dict() for d in result.duplicates_found],
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
        # Log full traceback for Render debugging
        print(f"❌ WARRANTY ANALYZE ERROR: {str(e)}")
        traceback.print_exc()
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
    
    # Indicate whether the original PDF is available
    pdf_file = WARRANTY_PDF_DIR / f"{claim_id}.pdf"
    claim["pdf_available"] = pdf_file.exists()
    
    return claim


@router.get("/claim/{claim_id}/pdf")
async def get_claim_pdf(claim_id: str):
    """
    Serve the original uploaded PDF for a claim.
    """
    pdf_file = WARRANTY_PDF_DIR / f"{claim_id}.pdf"
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="PDF not available for this claim")
    return FileResponse(
        path=str(pdf_file),
        media_type="application/pdf",
        filename=f"{claim_id}.pdf",
    )


@router.get("/duplicates/{claim_id}")
async def get_claim_duplicates(claim_id: str):
    """
    Get enriched duplicate audit for a claim.
    
    Returns grouped duplicates with:
    - Matched claim details (VIN, customer, issue, date, amounts)
    - All match reasons (IMAGE_EXACT, IMAGE_SIMILAR, VIN_ISSUE_DUPLICATE)
    - Reason summaries in plain English
    - Similarity scores and detection timestamps
    """
    claim = get_claim(claim_id)
    
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {claim_id} not found"
        )
    
    audit = get_duplicate_audit(claim_id)
    
    # Enrich each grouped entry with pdf_available
    for g in audit.get("grouped", []):
        cid = g.get("matched_claim_id")
        if cid:
            g["pdf_available"] = (WARRANTY_PDF_DIR / f"{cid}.pdf").exists()
        if g.get("claim_details"):
            g["claim_details"]["pdf_available"] = g.get("pdf_available", False)
    
    return audit


@router.get("/dashboard/overview")
async def dashboard_overview():
    """Dashboard overview: total claims, triage breakdown, suspicious count, duplicate stats."""
    from ..warranty.db import get_connection, release_connection, _get_cursor, _sql
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        
        cursor.execute("SELECT COUNT(*) as cnt FROM warranty_claims")
        total = _val(cursor.fetchone(), "cnt")
        
        cursor.execute("SELECT triage_class, COUNT(*) as cnt FROM warranty_claims GROUP BY triage_class")
        by_triage = {_val(r, "triage_class"): _val(r, "cnt") for r in cursor.fetchall()}
        
        cursor.execute("SELECT COUNT(*) as cnt FROM warranty_claims WHERE is_suspicious = 1")
        suspicious = _val(cursor.fetchone(), "cnt")
        
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM (
                SELECT claim_id_1 AS cid FROM warranty_duplicate_matches
                UNION
                SELECT claim_id_2 AS cid FROM warranty_duplicate_matches
            )
        """)
        dup_claims = _val(cursor.fetchone(), "cnt")
        
        cursor.execute("SELECT COUNT(*) as cnt FROM warranty_duplicate_matches")
        dup_matches = _val(cursor.fetchone(), "cnt")
        
        cursor.execute("SELECT COALESCE(AVG(risk_score), 0) as avg_risk FROM warranty_claims")
        avg_risk = round(_val(cursor.fetchone(), "avg_risk") or 0, 3)
        
        return {
            "total_claims": total,
            "by_triage": by_triage,
            "suspicious_count": suspicious,
            "claims_with_duplicates": dup_claims,
            "total_duplicate_matches": dup_matches,
            "avg_risk_score": avg_risk,
        }
    finally:
        release_connection(conn)


@router.get("/dashboard/root-causes")
async def dashboard_root_causes(
    limit: int = 20,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    issue: Optional[str] = None,
):
    """Claims grouped by issue type (root cause) with counts and avg amounts.
    Optionally filtered by brand, model, and/or issue."""
    from ..warranty.db import get_connection, release_connection, _get_cursor, _sql
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        conditions = ["issue_description IS NOT NULL", "issue_description != ''"]
        params = []
        if brand:
            conditions.append("brand = ?")
            params.append(brand)
        if model:
            conditions.append("model = ?")
            params.append(model)
        if issue:
            conditions.append("issue_description = ?")
            params.append(issue)
        where = "WHERE " + " AND ".join(conditions)
        cursor.execute(_sql(f"""
            SELECT issue_description,
                   COUNT(*) as claim_count,
                   COALESCE(AVG(total_amount), 0) as avg_amount,
                   COALESCE(SUM(total_amount), 0) as total_amount,
                   COALESCE(AVG(risk_score), 0) as avg_risk,
                   SUM(CASE WHEN is_suspicious = 1 THEN 1 ELSE 0 END) as suspicious_count
            FROM warranty_claims
            {where}
            GROUP BY issue_description
            ORDER BY claim_count DESC
            LIMIT {int(limit)}
        """), tuple(params))
        rows = [dict(r) for r in cursor.fetchall()]
        
        # Also return available filter options for dropdowns
        cursor.execute("SELECT DISTINCT brand FROM warranty_claims WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")
        brands = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT model FROM warranty_claims WHERE model IS NOT NULL AND model != '' ORDER BY model")
        models = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT issue_description FROM warranty_claims WHERE issue_description IS NOT NULL AND issue_description != '' ORDER BY issue_description")
        issues = [r[0] for r in cursor.fetchall()]
        
        return {"root_causes": rows, "brands": brands, "models": models, "issues": issues}
    finally:
        release_connection(conn)


@router.get("/dashboard/by-brand")
async def dashboard_by_brand():
    """Claims grouped by vehicle brand."""
    from ..warranty.db import get_connection, release_connection, _get_cursor
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute("""
            SELECT COALESCE(brand, 'Unknown') as brand,
                   COUNT(*) as claim_count,
                   COALESCE(AVG(total_amount), 0) as avg_amount,
                   COALESCE(SUM(total_amount), 0) as total_amount,
                   COALESCE(AVG(risk_score), 0) as avg_risk,
                   SUM(CASE WHEN is_suspicious = 1 THEN 1 ELSE 0 END) as suspicious_count
            FROM warranty_claims
            GROUP BY brand
            ORDER BY claim_count DESC
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        return {"brands": rows}
    finally:
        release_connection(conn)


@router.get("/dashboard/by-dealer")
async def dashboard_by_dealer(limit: int = 20):
    """Top dealers by claim count with risk metrics."""
    from ..warranty.db import get_connection, release_connection, _get_cursor
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute(f"""
            SELECT COALESCE(dealer_id, 'Unknown') as dealer_id,
                   COALESCE(dealer_name, dealer_id, 'Unknown') as dealer_name,
                   COUNT(*) as claim_count,
                   COALESCE(AVG(total_amount), 0) as avg_amount,
                   COALESCE(SUM(total_amount), 0) as total_amount,
                   COALESCE(AVG(risk_score), 0) as avg_risk,
                   SUM(CASE WHEN is_suspicious = 1 THEN 1 ELSE 0 END) as suspicious_count
            FROM warranty_claims
            GROUP BY dealer_id, dealer_name
            ORDER BY claim_count DESC
            LIMIT {int(limit)}
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        return {"dealers": rows}
    finally:
        release_connection(conn)


@router.get("/dashboard/signals")
async def dashboard_signal_frequency():
    """Fraud signal frequency across all claims."""
    from ..warranty.db import get_connection, release_connection, _get_cursor
    import json as _json
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute("SELECT fraud_signals FROM warranty_claims WHERE fraud_signals IS NOT NULL")
        
        signal_counts = {}
        severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        
        for row in cursor.fetchall():
            raw = row["fraud_signals"] if isinstance(row, dict) else row[0]
            if not raw:
                continue
            try:
                signals = _json.loads(raw) if isinstance(raw, str) else raw
                for sig in signals:
                    stype = sig.get("signal_type", "UNKNOWN")
                    signal_counts[stype] = signal_counts.get(stype, 0) + 1
                    sev = sig.get("severity", "LOW")
                    if sev in severity_counts:
                        severity_counts[sev] += 1
            except (_json.JSONDecodeError, TypeError):
                pass
        
        sorted_signals = sorted(signal_counts.items(), key=lambda x: -x[1])
        return {
            "signals": [{"signal_type": k, "count": v} for k, v in sorted_signals],
            "by_severity": severity_counts,
        }
    finally:
        release_connection(conn)


@router.get("/dashboard/duplicates")
async def dashboard_duplicate_overview():
    """Duplicate detection stats: by match type, top repeated claims."""
    from ..warranty.db import get_connection, release_connection, _get_cursor
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        
        # By match type
        cursor.execute("""
            SELECT match_type, COUNT(*) as cnt, AVG(similarity_score) as avg_sim
            FROM warranty_duplicate_matches
            GROUP BY match_type
            ORDER BY cnt DESC
        """)
        by_type = [dict(r) for r in cursor.fetchall()]
        
        # Claims with most duplicates
        cursor.execute("""
            SELECT claim_id, SUM(cnt) AS total_matches FROM (
                SELECT claim_id_1 AS claim_id, COUNT(*) AS cnt
                FROM warranty_duplicate_matches
                GROUP BY claim_id_1
                UNION ALL
                SELECT claim_id_2 AS claim_id, COUNT(*) AS cnt
                FROM warranty_duplicate_matches
                GROUP BY claim_id_2
            ) AS sub
            GROUP BY claim_id
            ORDER BY total_matches DESC
            LIMIT 10
        """)
        top_claims = [dict(r) for r in cursor.fetchall()]
        
        return {"by_type": by_type, "top_claims_with_duplicates": top_claims}
    finally:
        release_connection(conn)


@router.get("/dashboard/trends")
async def dashboard_trends():
    """Claims over time (by month)."""
    from ..warranty.db import get_connection, release_connection, _get_cursor
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute("""
            SELECT SUBSTR(claim_date, 1, 7) as month,
                   COUNT(*) as claim_count,
                   COALESCE(AVG(total_amount), 0) as avg_amount,
                   COALESCE(AVG(risk_score), 0) as avg_risk,
                   SUM(CASE WHEN is_suspicious = 1 THEN 1 ELSE 0 END) as suspicious_count
            FROM warranty_claims
            WHERE claim_date IS NOT NULL AND LENGTH(claim_date) >= 7
            GROUP BY SUBSTR(claim_date, 1, 7)
            ORDER BY month
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        return {"trends": rows}
    finally:
        release_connection(conn)


@router.get("/dashboard/claims")
async def dashboard_claims_list(
    issue: Optional[str] = None,
    brand: Optional[str] = None,
    dealer_id: Optional[str] = None,
    triage: Optional[str] = None,
    suspicious_only: bool = False,
    duplicates_only: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    """Drill-down: list claims filtered by issue, brand, dealer, triage, or duplicates."""
    from ..warranty.db import get_connection, release_connection, _get_cursor, _sql
    
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        
        conditions = []
        params = []
        
        if issue:
            conditions.append("issue_description = ?")
            params.append(issue)
        if brand:
            conditions.append("brand = ?")
            params.append(brand)
        if dealer_id:
            conditions.append("dealer_id = ?")
            params.append(dealer_id)
        if triage:
            conditions.append("triage_class = ?")
            params.append(triage)
        if suspicious_only:
            conditions.append("is_suspicious = 1")
        if duplicates_only:
            conditions.append("""id IN (
                SELECT claim_id_1 FROM warranty_duplicate_matches
                UNION
                SELECT claim_id_2 FROM warranty_duplicate_matches
            )""")
        
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        
        cursor.execute(_sql(f"""
            SELECT id, customer_name, dealer_id, dealer_name, vin, brand, model, year,
                   issue_description, claim_date, total_amount, risk_score, triage_class,
                   is_suspicious, status, created_at
            FROM warranty_claims
            {where}
            ORDER BY created_at DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
        """), tuple(params))
        
        claims = [dict(r) for r in cursor.fetchall()]
        
        # Get total count
        cursor.execute(_sql(f"SELECT COUNT(*) as cnt FROM warranty_claims {where}"), tuple(params))
        total = _val(cursor.fetchone(), "cnt")
        
        return {"claims": claims, "total": total, "limit": limit, "offset": offset}
    finally:
        release_connection(conn)


def _val(row, key):
    """Extract value from a DB row (handles dict, sqlite3.Row, and tuple rows)."""
    if row is None:
        return 0
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        try:
            return row[0]
        except (IndexError, TypeError):
            return 0


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
