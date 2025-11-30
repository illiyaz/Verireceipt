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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import asyncio
import json as json_module

from app.pipelines.rules import analyze_receipt
from app.repository.receipt_store import get_receipt_store

# Import hybrid analysis engines
try:
    from app.pipelines.vision_llm import analyze_receipt_with_vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

try:
    from app.pipelines.donut_extractor import extract_receipt_with_donut, DONUT_AVAILABLE
except ImportError:
    DONUT_AVAILABLE = False

try:
    from app.pipelines.layoutlm_extractor import extract_receipt_with_layoutlm, LAYOUTLM_AVAILABLE
except ImportError:
    LAYOUTLM_AVAILABLE = False

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


# ---------- Hybrid Analysis Endpoint ----------

class HybridAnalyzeResponse(BaseModel):
    """Response from hybrid 4-engine analysis."""
    rule_based: dict = Field(..., description="Rule-based engine results")
    donut: Optional[dict] = Field(None, description="DONUT extraction results")
    layoutlm: Optional[dict] = Field(None, description="LayoutLM extraction results")
    vision_llm: Optional[dict] = Field(None, description="Vision LLM results")
    hybrid_verdict: dict = Field(..., description="Combined verdict from all engines")
    timing: dict = Field(..., description="Timing information for each engine")
    engines_used: List[str] = Field(..., description="List of engines that were used")


@app.post("/analyze/hybrid", response_model=HybridAnalyzeResponse, tags=["analysis"])
async def analyze_hybrid(file: UploadFile = File(...)):
    """
    Analyze receipt using all 4 engines in parallel:
    1. Rule-Based (OCR + Metadata + Rules) - Fast, reliable baseline
    2. DONUT (Document Understanding Transformer) - Specialized for receipts
    3. LayoutLM (Multimodal Document Understanding) - Best for diverse formats
    4. Vision LLM (Ollama) - Visual fraud detection
    
    Returns results from all engines plus a hybrid verdict.
    """
    from concurrent.futures import ThreadPoolExecutor
    import time as time_module
    
    # Save uploaded file
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )
    
    results = {
        "rule_based": None,
        "donut": None,
        "layoutlm": None,
        "vision_llm": None,
        "hybrid_verdict": None,
        "timing": {},
        "engines_used": []
    }
    
    # Run all engines in parallel
    def run_rule_based():
        start = time_module.time()
        try:
            decision = analyze_receipt(str(temp_path))
            elapsed = time_module.time() - start
            return {
                "label": decision.label,
                "score": decision.score,
                "reasons": decision.reasons,
                "minor_notes": decision.minor_notes,
                "time_seconds": round(elapsed, 2)
            }
        except Exception as e:
            return {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
    
    def run_donut():
        if not DONUT_AVAILABLE:
            return {"error": "DONUT not available", "time_seconds": 0}
        
        start = time_module.time()
        try:
            data = extract_receipt_with_donut(str(temp_path))
            elapsed = time_module.time() - start
            return {
                "merchant": data.get("merchant"),
                "total": data.get("total"),
                "line_items_count": len(data.get("line_items", [])),
                "data_quality": "good" if data.get("total") else "poor",
                "time_seconds": round(elapsed, 2)
            }
        except Exception as e:
            return {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
    
    def run_layoutlm():
        if not LAYOUTLM_AVAILABLE:
            return {"error": "LayoutLM not available", "time_seconds": 0}
        
        start = time_module.time()
        try:
            data = extract_receipt_with_layoutlm(str(temp_path), method="simple")
            elapsed = time_module.time() - start
            return {
                "merchant": data.get("merchant"),
                "total": data.get("total"),
                "date": data.get("date"),
                "words_extracted": data.get("words_extracted", 0),
                "data_quality": data.get("data_quality", "unknown"),
                "confidence": data.get("confidence", "unknown"),
                "time_seconds": round(elapsed, 2)
            }
        except Exception as e:
            return {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
    
    def run_vision():
        if not VISION_AVAILABLE:
            return {"error": "Vision LLM not available", "time_seconds": 0}
        
        start = time_module.time()
        try:
            vision_results = analyze_receipt_with_vision(str(temp_path))
            elapsed = time_module.time() - start
            auth = vision_results.get("authenticity_assessment", {})
            fraud = vision_results.get("fraud_detection", {})
            return {
                "verdict": auth.get("verdict", "unknown"),
                "confidence": auth.get("confidence", 0.0),
                "authenticity_score": auth.get("authenticity_score", 0.0),
                "fraud_indicators": fraud.get("fraud_indicators", []),
                "reasoning": auth.get("reasoning", ""),
                "time_seconds": round(elapsed, 2)
            }
        except Exception as e:
            return {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
    
    # Execute all 4 engines in parallel
    start_time = time_module.time()
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        rule_future = executor.submit(run_rule_based)
        donut_future = executor.submit(run_donut)
        layoutlm_future = executor.submit(run_layoutlm)
        vision_future = executor.submit(run_vision)
        
        results["rule_based"] = rule_future.result()
        results["donut"] = donut_future.result()
        results["layoutlm"] = layoutlm_future.result()
        results["vision_llm"] = vision_future.result()
    
    total_time = time_module.time() - start_time
    results["timing"]["parallel_total_seconds"] = round(total_time, 2)
    
    # Track which engines were used
    if not results["rule_based"].get("error"):
        results["engines_used"].append("rule-based")
    if not results["donut"].get("error"):
        results["engines_used"].append("donut")
    if not results["layoutlm"].get("error"):
        results["engines_used"].append("layoutlm")
    if not results["vision_llm"].get("error"):
        results["engines_used"].append("vision-llm")
    
    # Generate hybrid verdict
    hybrid = {
        "final_label": "unknown",
        "confidence": 0.0,
        "recommended_action": "unknown",
        "reasoning": [],
        "engines_completed": len(results["engines_used"]),
        "total_engines": 4
    }
    
    # Check if all engines completed successfully
    all_engines_completed = (
        not results["rule_based"].get("error") and
        not results["donut"].get("error") and
        not results["layoutlm"].get("error") and
        not results["vision_llm"].get("error")
    )
    
    # If not all engines completed, flag for review
    if not all_engines_completed:
        hybrid["final_label"] = "incomplete"
        hybrid["confidence"] = 0.0
        hybrid["recommended_action"] = "retry_or_review"
        
        # Add reasoning for each failed engine
        if results["rule_based"].get("error"):
            hybrid["reasoning"].append(f"Rule-based engine failed: {results['rule_based']['error']}")
        if results["donut"].get("error"):
            hybrid["reasoning"].append(f"DONUT engine failed: {results['donut']['error']}")
        if results["layoutlm"].get("error"):
            hybrid["reasoning"].append(f"LayoutLM engine failed: {results['layoutlm']['error']}")
        if results["vision_llm"].get("error"):
            hybrid["reasoning"].append(f"Vision LLM failed: {results['vision_llm']['error']}")
        
        if not hybrid["reasoning"]:
            hybrid["reasoning"].append("One or more engines did not complete successfully")
    else:
        # All engines completed - generate hybrid verdict
        rule_label = results["rule_based"].get("label", "unknown")
        rule_score = results["rule_based"].get("score", 0.5)
        vision_verdict = results["vision_llm"].get("verdict", "unknown")
        vision_confidence = results["vision_llm"].get("confidence", 0.0)
        donut_quality = results["donut"].get("data_quality", "unknown")
        layoutlm_quality = results["layoutlm"].get("data_quality", "unknown")
        
        # Combine signals from all 4 engines
        if rule_label == "real" and rule_score < 0.3:
            if vision_verdict == "real" and vision_confidence > 0.7:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.98  # Higher with 4 engines
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("All 4 engines indicate authentic receipt")
                if donut_quality == "good" or layoutlm_quality == "good":
                    hybrid["reasoning"].append("Document structure validated by extraction engines")
            else:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.85
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("Rule-based engine indicates real receipt")
        elif rule_label == "fake" or rule_score > 0.7:
            hybrid["final_label"] = "fake"
            hybrid["confidence"] = 0.90
            hybrid["recommended_action"] = "reject"
            hybrid["reasoning"].append("High fraud score detected by rule-based engine")
        else:
            # Suspicious case - use vision as tiebreaker
            if vision_verdict == "fake" and vision_confidence > 0.7:
                hybrid["final_label"] = "fake"
                hybrid["confidence"] = 0.85
                hybrid["recommended_action"] = "reject"
                hybrid["reasoning"].append("Vision model detected fraud indicators")
            elif vision_verdict == "real" and vision_confidence > 0.8:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.80
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("Vision model confirms authenticity")
            else:
                hybrid["final_label"] = "suspicious"
                hybrid["confidence"] = 0.60
                hybrid["recommended_action"] = "human_review"
                hybrid["reasoning"].append("Uncertain - requires human review")
    
    results["hybrid_verdict"] = hybrid
    
    # Cleanup
    try:
        temp_path.unlink()
    except:
        pass
    
    return HybridAnalyzeResponse(**results)


# ---------- Streaming Analysis Endpoint ----------

@app.post("/analyze/hybrid/stream", tags=["analysis"])
async def analyze_hybrid_stream(file: UploadFile = File(...)):
    """
    Analyze receipt with real-time streaming updates.
    
    Returns Server-Sent Events (SSE) stream with updates as each engine completes:
    - event: engine_start - When an engine starts
    - event: engine_complete - When an engine finishes
    - event: analysis_complete - Final hybrid verdict
    """
    from concurrent.futures import ThreadPoolExecutor
    import time as time_module
    import queue
    
    # Save uploaded file
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )
    
    # Queue for streaming updates
    update_queue = queue.Queue()
    
    results = {
        "rule_based": None,
        "donut": None,
        "vision_llm": None,
        "hybrid_verdict": None,
        "timing": {},
        "engines_used": []
    }
    
    def run_rule_based():
        update_queue.put({"event": "engine_start", "engine": "rule-based"})
        start = time_module.time()
        try:
            decision = analyze_receipt(str(temp_path))
            elapsed = time_module.time() - start
            result = {
                "label": decision.label,
                "score": decision.score,
                "reasons": decision.reasons,
                "minor_notes": decision.minor_notes,
                "time_seconds": round(elapsed, 2)
            }
            update_queue.put({
                "event": "engine_complete",
                "engine": "rule-based",
                "data": result
            })
            return result
        except Exception as e:
            error_result = {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
            update_queue.put({
                "event": "engine_complete",
                "engine": "rule-based",
                "data": error_result
            })
            return error_result
    
    def run_donut():
        if not DONUT_AVAILABLE:
            return {"error": "DONUT not available", "time_seconds": 0}
        
        update_queue.put({"event": "engine_start", "engine": "donut"})
        start = time_module.time()
        try:
            data = extract_receipt_with_donut(str(temp_path))
            elapsed = time_module.time() - start
            result = {
                "merchant": data.get("merchant"),
                "total": data.get("total"),
                "line_items_count": len(data.get("line_items", [])),
                "data_quality": "good" if data.get("total") else "poor",
                "time_seconds": round(elapsed, 2)
            }
            update_queue.put({
                "event": "engine_complete",
                "engine": "donut",
                "data": result
            })
            return result
        except Exception as e:
            error_result = {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
            update_queue.put({
                "event": "engine_complete",
                "engine": "donut",
                "data": error_result
            })
            return error_result
    
    def run_vision():
        if not VISION_AVAILABLE:
            return {"error": "Vision LLM not available", "time_seconds": 0}
        
        update_queue.put({"event": "engine_start", "engine": "vision-llm"})
        start = time_module.time()
        try:
            vision_results = analyze_receipt_with_vision(str(temp_path))
            elapsed = time_module.time() - start
            auth = vision_results.get("authenticity_assessment", {})
            fraud = vision_results.get("fraud_detection", {})
            result = {
                "verdict": auth.get("verdict", "unknown"),
                "confidence": auth.get("confidence", 0.0),
                "authenticity_score": auth.get("authenticity_score", 0.0),
                "fraud_indicators": fraud.get("fraud_indicators", []),
                "reasoning": auth.get("reasoning", ""),
                "time_seconds": round(elapsed, 2)
            }
            update_queue.put({
                "event": "engine_complete",
                "engine": "vision-llm",
                "data": result
            })
            return result
        except Exception as e:
            error_result = {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
            update_queue.put({
                "event": "engine_complete",
                "engine": "vision-llm",
                "data": error_result
            })
            return error_result
    
    async def event_generator():
        """Generate SSE events as engines complete."""
        
        # Send initial event
        yield f"event: analysis_start\ndata: {json_module.dumps({'message': 'Starting 3-engine analysis'})}\n\n"
        
        # Start all engines in parallel
        loop = asyncio.get_event_loop()
        start_time = time_module.time()
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            rule_future = loop.run_in_executor(executor, run_rule_based)
            donut_future = loop.run_in_executor(executor, run_donut)
            vision_future = loop.run_in_executor(executor, run_vision)
            
            # Stream updates as they come
            engines_completed = 0
            while engines_completed < 3:
                try:
                    # Check queue for updates (non-blocking with timeout)
                    update = update_queue.get(timeout=0.1)
                    
                    event_type = update["event"]
                    data = json_module.dumps(update)
                    
                    yield f"event: {event_type}\ndata: {data}\n\n"
                    
                    if event_type == "engine_complete":
                        engines_completed += 1
                        
                except queue.Empty:
                    # No updates, just continue
                    await asyncio.sleep(0.1)
            
            # Wait for all futures to complete
            results["rule_based"] = await rule_future
            results["donut"] = await donut_future
            results["vision_llm"] = await vision_future
        
        total_time = time_module.time() - start_time
        results["timing"]["parallel_total_seconds"] = round(total_time, 2)
        
        # Track which engines were used
        if not results["rule_based"].get("error"):
            results["engines_used"].append("rule-based")
        if not results["donut"].get("error"):
            results["engines_used"].append("donut")
        if not results["vision_llm"].get("error"):
            results["engines_used"].append("vision-llm")
        
        # Generate hybrid verdict
        hybrid = {
            "final_label": "unknown",
            "confidence": 0.0,
            "recommended_action": "unknown",
            "reasoning": []
        }
        
        rule_label = results["rule_based"].get("label", "unknown")
        rule_score = results["rule_based"].get("score", 0.5)
        vision_verdict = results["vision_llm"].get("verdict", "unknown")
        vision_confidence = results["vision_llm"].get("confidence", 0.0)
        
        # Simple hybrid logic
        if rule_label == "real" and rule_score < 0.3:
            if vision_verdict == "real" and vision_confidence > 0.7:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.95
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("Both engines strongly indicate authentic receipt")
            else:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.85
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("Rule-based engine indicates real receipt")
        elif rule_label == "fake" or rule_score > 0.7:
            hybrid["final_label"] = "fake"
            hybrid["confidence"] = 0.90
            hybrid["recommended_action"] = "reject"
            hybrid["reasoning"].append("High fraud score detected")
        else:
            if vision_verdict == "fake" and vision_confidence > 0.7:
                hybrid["final_label"] = "fake"
                hybrid["confidence"] = 0.85
                hybrid["recommended_action"] = "reject"
                hybrid["reasoning"].append("Vision model detected fraud indicators")
            elif vision_verdict == "real" and vision_confidence > 0.8:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.80
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("Vision model confirms authenticity")
            else:
                hybrid["final_label"] = "suspicious"
                hybrid["confidence"] = 0.60
                hybrid["recommended_action"] = "human_review"
                hybrid["reasoning"].append("Uncertain - requires human review")
        
        results["hybrid_verdict"] = hybrid
        
        # Send final event with complete results
        yield f"event: analysis_complete\ndata: {json_module.dumps(results)}\n\n"
        
        # Cleanup
        try:
            temp_path.unlink()
        except:
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )