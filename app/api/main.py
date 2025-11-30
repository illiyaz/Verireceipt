# app/api/main.py

from typing import List, Optional, Union, Literal
import os
import shutil
import uuid
from pathlib import Path
import time
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.pipelines.rules import analyze_receipt
from app.repository.receipt_store import get_receipt_store

app = FastAPI(
    title="VeriReceipt API",
    description="AI-Powered Fake Receipt Detection Engine. Analyzes receipts using document forensics, OCR, metadata analysis, and rule-based fraud detection.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for web demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use our repository abstraction (CSV or DB) based on env
store = get_receipt_store()

# Directory inside container where we temporarily save uploaded receipts
UPLOAD_DIR = Path(os.getenv("VERIRECEIPT_UPLOAD_DIR", "/tmp/verireceipt_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Pydantic models ----------

class AnalyzeResponse(BaseModel):
    label: str = Field(..., description="Classification: real, suspicious, or fake")
    score: float = Field(..., description="Fraud score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasons: List[str] = Field(..., description="Main reasons for the classification")
    minor_notes: List[str] = Field(default=[], description="Low-severity observations")
    processing_time_ms: Optional[float] = Field(None, description="Analysis time in milliseconds")
    # Backend references (DB backend may return proper IDs; CSV backend may return filename)
    receipt_ref: Optional[Union[int, str]] = None
    analysis_ref: Optional[Union[int, str]] = None


class BatchAnalyzeResponse(BaseModel):
    results: List[AnalyzeResponse]
    total_processed: int
    total_time_ms: float


class StatsResponse(BaseModel):
    total_analyses: int
    real_count: int
    suspicious_count: int
    fake_count: int
    avg_score: float
    last_updated: str


class FeedbackRequest(BaseModel):
    # For DB backend: these would be integer IDs.
    # For CSV backend we might use filename or analysis_ref string.
    receipt_ref: Optional[Union[int, str]] = None
    analysis_ref: Optional[Union[int, str]] = None

    given_label: Literal["real", "fake", "suspicious"]
    reviewer_id: Optional[str] = None
    comment: Optional[str] = None
    reason_code: Optional[str] = None


class FeedbackResponse(BaseModel):
    feedback_ref: Optional[Union[int, str]] = None
    message: str


# ---------- Utility helpers ----------

def _save_upload_to_disk(upload: UploadFile) -> Path:
    """
    Save uploaded file to a temp path inside the container.

    We keep it simple:
    - generate a random UUID-based filename
    - preserve original extension
    """
    suffix = Path(upload.filename or "").suffix
    tmp_name = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / tmp_name

    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)

    return dest


# ---------- API endpoints ----------

@app.get("/health", tags=["meta"])
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "ok",
        "service": "VeriReceipt",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/", tags=["meta"])
def root():
    """Root endpoint with API information."""
    return {
        "service": "VeriReceipt API",
        "version": "0.1.0",
        "description": "AI-Powered Fake Receipt Detection Engine",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/analyze", response_model=AnalyzeResponse, tags=["analysis"])
async def analyze_endpoint(file: UploadFile = File(..., description="Receipt file (PDF, JPG, PNG)")):
    """
    Analyze a single uploaded receipt (PDF/image) and return:
    - **label**: real / fake / suspicious
    - **score**: 0.0–1.0 fraud probability
    - **reasons**: Human-readable explanations
    - **minor_notes**: Low-severity observations
    - **processing_time_ms**: Analysis duration
    
    Supported formats: PDF, JPG, JPEG, PNG
    """
    # Validate file type
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # 1. Save to temp file inside container
    tmp_path = _save_upload_to_disk(file)
    start_time = time.time()

    try:
        # 2. Run our rules pipeline
        decision = analyze_receipt(str(tmp_path))
        processing_time_ms = (time.time() - start_time) * 1000

        # 3. Persist via repository (CSV or DB)
        analysis_ref = store.save_analysis(str(tmp_path), decision)
        # For DB backend, we may have a numeric analysis_id; for CSV, maybe filename.
        # For now, we don't expose receipt_id separately unless DB backend needs it.

        return AnalyzeResponse(
            label=decision.label,
            score=decision.score,
            reasons=decision.reasons,
            minor_notes=decision.minor_notes or [],
            processing_time_ms=round(processing_time_ms, 2),
            receipt_ref=None,          # can be filled once we expose receipt_id from store
            analysis_ref=analysis_ref,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )
    finally:
        # 4. Best-effort cleanup
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/feedback", response_model=FeedbackResponse, tags=["feedback"])
async def feedback_endpoint(payload: FeedbackRequest):
    """
    Capture human feedback / override for a specific analysis.

    NOTE:
    - In CSV mode, this may be a no-op until we implement feedback CSV.
    - In DB mode, this will write into the feedback table.
    """
    # Very simple behavior: delegate to store.save_feedback.
    # Different backends can interpret receipt_ref/analysis_ref appropriately.
    try:
        feedback_ref = store.save_feedback(
            receipt_identifier=payload.receipt_ref,
            analysis_identifier=payload.analysis_ref,
            given_label=payload.given_label,
            reviewer_id=payload.reviewer_id,
            comment=payload.comment,
            reason_code=payload.reason_code,
        )
    except NotImplementedError:
        # If CSV backend doesn't support feedback yet
        raise HTTPException(
            status_code=501,
            detail="Feedback not implemented for this backend (CSV). Switch to DB backend.",
        )

    return FeedbackResponse(
        feedback_ref=feedback_ref,
        message="Feedback recorded successfully.",
    )


@app.post("/analyze/batch", response_model=BatchAnalyzeResponse, tags=["analysis"])
async def batch_analyze_endpoint(files: List[UploadFile] = File(..., description="Multiple receipt files")):
    """
    Analyze multiple receipts in a single request.
    
    Returns analysis results for each receipt along with aggregate statistics.
    """
    if len(files) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 files per batch request"
        )
    
    results = []
    start_time = time.time()
    
    for file in files:
        # Validate file type
        allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
        file_ext = Path(file.filename or "").suffix.lower()
        if file_ext not in allowed_extensions:
            # Skip invalid files but continue processing
            continue
        
        tmp_path = _save_upload_to_disk(file)
        file_start = time.time()
        
        try:
            decision = analyze_receipt(str(tmp_path))
            processing_time_ms = (time.time() - file_start) * 1000
            analysis_ref = store.save_analysis(str(tmp_path), decision)
            
            results.append(AnalyzeResponse(
                label=decision.label,
                score=decision.score,
                reasons=decision.reasons,
                minor_notes=decision.minor_notes or [],
                processing_time_ms=round(processing_time_ms, 2),
                receipt_ref=None,
                analysis_ref=analysis_ref,
            ))
        except Exception:
            # Skip failed files but continue processing
            continue
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    
    total_time_ms = (time.time() - start_time) * 1000
    
    return BatchAnalyzeResponse(
        results=results,
        total_processed=len(results),
        total_time_ms=round(total_time_ms, 2)
    )


@app.get("/stats", response_model=StatsResponse, tags=["analytics"])
def get_stats():
    """
    Get aggregate statistics about all analyzed receipts.
    
    Returns counts by classification, average fraud score, and last update time.
    """
    try:
        stats = store.get_statistics()
        return StatsResponse(
            total_analyses=stats.get("total_analyses", 0),
            real_count=stats.get("real_count", 0),
            suspicious_count=stats.get("suspicious_count", 0),
            fake_count=stats.get("fake_count", 0),
            avg_score=round(stats.get("avg_score", 0.0), 3),
            last_updated=datetime.utcnow().isoformat()
        )
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Statistics not implemented for this backend (CSV). Switch to DB backend."
        )