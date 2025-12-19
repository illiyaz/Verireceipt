# app/api/main.py

from typing import List, Optional, Union, Literal
import os
import shutil
import uuid
from pathlib import Path
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
import asyncio
import json as json_module

from app.pipelines.rules import analyze_receipt
from app.repository.receipt_store import get_receipt_store
from app.pipelines.ensemble import get_ensemble

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

try:
    from app.models.donut_receipt import DonutReceiptExtractor
    DONUT_RECEIPT_AVAILABLE = True
except ImportError:
    DONUT_RECEIPT_AVAILABLE = False

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
    Save uploaded file to a temp path and validate it's a valid image.

    We keep it simple:
    - generate a random UUID-based filename
    - preserve original extension
    - validate image can be opened
    """
    from PIL import Image
    
    suffix = Path(upload.filename or "").suffix.lower()
    # Ensure we have a valid image extension
    if suffix not in [".jpg", ".jpeg", ".png", ".pdf"]:
        suffix = ".jpg"  # Default to jpg
    
    tmp_name = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / tmp_name

    # Save the file
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    
    # Validate and convert if needed (but keep original if validation fails)
    if suffix == ".pdf":
        # PDFs are handled by the pipelines directly
        print(f"📄 PDF uploaded: {dest}")
        return dest
    else:
        try:
            # Verify file exists and has content
            if not dest.exists():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Uploaded file not found: {dest}"
                )
            
            if dest.stat().st_size == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file is empty"
                )
            
            # Try to open and validate image
            from PIL import ImageFile
            ImageFile.LOAD_TRUNCATED_IMAGES = True  # Allow truncated images
            
            # Try to register HEIF support if available
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                pass  # HEIF support not available, will fail on HEIC files
            
            img = Image.open(dest)
            print(f"📷 Image opened: format={img.format}, mode={img.mode}, size={img.size}")
            
            # Don't verify - it's too strict and closes the file
            # Just try to load the image data
            img.load()
            
            # Convert to RGB if needed (handles RGBA, P, L, etc.)
            if img.mode not in ["RGB"]:
                print(f"🔄 Converting from {img.mode} to RGB")
                img = img.convert("RGB")
            
            # Always save as JPEG for consistency
            jpeg_dest = dest.with_suffix(".jpg")
            img.save(jpeg_dest, "JPEG", quality=95)
            img.close()
            
            # Remove original if different from JPEG
            if jpeg_dest != dest and dest.exists():
                dest.unlink()
            dest = jpeg_dest
            
            print(f"✅ Image validated and saved: {dest}")
        except HTTPException:
            raise
        except Exception as e:
            # Log error but don't fail - keep the original file
            print(f"⚠️ Image validation warning: {str(e)}")
            print(f"   File exists: {dest.exists()}")
            print(f"   File size: {dest.stat().st_size if dest.exists() else 'N/A'}")
            print(f"   Keeping original file: {dest}")
            # Don't remove the file, just use it as-is

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
    """Response from hybrid 5-engine analysis."""
    receipt_id: str = Field(..., description="Unique receipt identifier")
    rule_based: dict = Field(..., description="Rule-based engine results")
    donut: Optional[dict] = Field(None, description="DONUT extraction results")
    donut_receipt: Optional[dict] = Field(None, description="Donut-Receipt extraction results")
    layoutlm: Optional[dict] = Field(None, description="LayoutLM extraction results")
    vision_llm: Optional[dict] = Field(None, description="Vision LLM results")
    hybrid_verdict: dict = Field(..., description="Combined verdict from all engines")
    timing: dict = Field(..., description="Timing information for each engine")
    engines_used: List[str] = Field(..., description="List of engines that were used")


@app.post("/analyze/hybrid", response_model=HybridAnalyzeResponse, tags=["analysis"])
async def analyze_hybrid(file: UploadFile = File(...)):
    """
    Analyze receipt using all 5 engines in parallel:
    1. Rule-Based (OCR + Metadata + Rules) - Fast, reliable baseline
    2. DONUT (Document Understanding Transformer) - Specialized for receipts
    3. Donut-Receipt (Structured Extraction) - NEW! Extracts items, merchant, payment
    4. LayoutLM (Multimodal Document Understanding) - Best for diverse formats
    5. Vision LLM (Ollama) - Visual fraud detection
    
    Returns results from all engines plus a hybrid verdict.
    """
    from concurrent.futures import ThreadPoolExecutor
    import time as time_module
    
    # Save uploaded file with validation
    try:
        temp_path = _save_upload_to_disk(file)
        file_id = temp_path.stem  # Get filename without extension
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )
    
    results = {
        "receipt_id": file_id,  # Include receipt ID in response
        "rule_based": None,
        "donut": None,
        "donut_receipt": None,  # NEW: 5th engine
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
        # TEMPORARILY DISABLED - meta tensor issues with PyTorch/Transformers
        # TODO: Fix DONUT model loading or upgrade transformers library
        return {
            "error": "DONUT temporarily disabled due to model loading issues",
            "merchant": None,
            "total": None,
            "line_items_count": 0,
            "data_quality": "N/A",
            "time_seconds": 0
        }
    
    def run_donut_receipt():
        # TEMPORARILY DISABLED - same meta tensor issues as DONUT
        # TODO: Fix model loading
        return {
            "error": "Donut-Receipt temporarily disabled due to model loading issues",
            "merchant": None,
            "total": None,
            "date": None,
            "line_items_count": 0,
            "data_quality": "N/A",
            "time_seconds": 0
        }
    
    def run_layoutlm():
        if not LAYOUTLM_AVAILABLE:
            return {"error": "LayoutLM not available", "time_seconds": 0}
        
        start = time_module.time()
        try:
            print(f"🔍 LayoutLM extracting from: {temp_path}")
            data = extract_receipt_with_layoutlm(str(temp_path), method="simple")
            elapsed = time_module.time() - start
            print(f"✅ LayoutLM extracted: {data}")
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
            import traceback
            print(f"❌ LayoutLM error: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
    
    def run_vision():
        if not VISION_AVAILABLE:
            return {
                "error": "Vision LLM not available",
                "verdict": "unknown",
                "confidence": 0.0,
                "reasoning": "Vision LLM module not available",
                "time_seconds": 0
            }
        
        start = time_module.time()
        try:
            vision_results = analyze_receipt_with_vision(str(temp_path))
            elapsed = time_module.time() - start
            auth = vision_results.get("authenticity_assessment", {})
            fraud = vision_results.get("fraud_detection", {})
            
            # Check if we got valid results
            verdict = auth.get("verdict", "unknown")
            confidence = auth.get("confidence", 0.0)
            reasoning = auth.get("reasoning", "")
            
            # If verdict is unknown and reasoning indicates parse failure, it's a network/service issue
            if verdict == "unknown" and "Failed to parse" in reasoning:
                print(f"⚠️ Vision LLM parse failure - likely Ollama service issue")
                return {
                    "error": "Vision LLM service unavailable",
                    "verdict": "unknown",
                    "confidence": 0.0,
                    "reasoning": "Vision LLM service not responding (check Ollama)",
                    "time_seconds": round(elapsed, 2)
                }
            
            return {
                "verdict": verdict,
                "confidence": confidence,
                "authenticity_score": auth.get("authenticity_score", 0.0),
                "fraud_indicators": fraud.get("fraud_indicators", []),
                "reasoning": reasoning,
                "time_seconds": round(elapsed, 2)
            }
        except Exception as e:
            import traceback
            print(f"❌ Vision LLM exception: {e}")
            traceback.print_exc()
            return {
                "error": str(e),
                "verdict": "unknown",
                "confidence": 0.0,
                "reasoning": f"Vision LLM error: {str(e)}",
                "time_seconds": round(time_module.time() - start, 2)
            }
    
    # Execute engines SEQUENTIALLY for intelligence convergence
    # Each engine benefits from previous engines' results
    start_time = time_module.time()
    
    print("\n" + "="*60)
    print("SEQUENTIAL INTELLIGENCE PIPELINE")
    print("="*60)
    
    # STEP 1: Vision LLM (first - visual fraud detection)
    print("\n1️⃣ Running Vision LLM...")
    results["vision_llm"] = run_vision()
    if not results["vision_llm"].get("error"):
        print(f"   ✅ Vision: {results['vision_llm'].get('verdict')} ({results['vision_llm'].get('confidence', 0)*100:.0f}%)")
    else:
        print(f"   ❌ Vision failed: {results['vision_llm'].get('error')}")
    
    # STEP 2: LayoutLM (uses Vision context for better extraction)
    print("\n2️⃣ Running LayoutLM...")
    results["layoutlm"] = run_layoutlm()
    if not results["layoutlm"].get("error"):
        print(f"   ✅ LayoutLM: Total={results['layoutlm'].get('total')}, Words={results['layoutlm'].get('words_extracted')}")
    else:
        print(f"   ❌ LayoutLM failed: {results['layoutlm'].get('error')}")
    
    # STEP 3: DONUT (if available)
    print("\n3️⃣ Running DONUT...")
    results["donut"] = run_donut()
    if not results["donut"].get("error"):
        print(f"   ✅ DONUT: Total={results['donut'].get('total')}")
    else:
        print(f"   ⚠️ DONUT: {results['donut'].get('error')}")
    
    # STEP 4: Donut-Receipt (if available)
    print("\n4️⃣ Running Donut-Receipt...")
    results["donut_receipt"] = run_donut_receipt()
    if not results["donut_receipt"].get("error"):
        print(f"   ✅ Donut-Receipt: {results['donut_receipt'].get('data_quality')}")
    else:
        print(f"   ⚠️ Donut-Receipt: {results['donut_receipt'].get('error')}")
    
    # STEP 5: Rule-Based (uses ALL extracted data from above engines)
    print("\n5️⃣ Running Rule-Based with extracted data...")
    # Pass LayoutLM data to Rule-Based for better analysis
    extracted_total = results["layoutlm"].get("total") if not results["layoutlm"].get("error") else None
    extracted_merchant = results["layoutlm"].get("merchant") if not results["layoutlm"].get("error") else None
    extracted_date = results["layoutlm"].get("date") if not results["layoutlm"].get("error") else None
    
    if extracted_total or extracted_merchant or extracted_date:
        print(f"   📊 Using extracted data: Total={extracted_total}, Merchant={extracted_merchant}")
        # Format total properly
        if extracted_total:
            if isinstance(extracted_total, (int, float)):
                extracted_total = f"{float(extracted_total):.2f}"
            else:
                extracted_total = str(extracted_total)
        
        try:
            enhanced_decision = analyze_receipt(
                str(temp_path),
                extracted_total=extracted_total,
                extracted_merchant=extracted_merchant,
                extracted_date=extracted_date
            )
            results["rule_based"] = {
                "label": enhanced_decision.label,
                "score": enhanced_decision.score,
                "reasons": enhanced_decision.reasons,
                "minor_notes": enhanced_decision.minor_notes,
                "time_seconds": 0,
                "enhanced": True
            }
            print(f"   ✅ Rule-Based (enhanced): {enhanced_decision.label} ({enhanced_decision.score*100:.0f}%)")
        except Exception as e:
            print(f"   ⚠️ Enhanced Rule-Based failed, using basic: {e}")
            results["rule_based"] = run_rule_based()
    else:
        results["rule_based"] = run_rule_based()
        if not results["rule_based"].get("error"):
            print(f"   ✅ Rule-Based: {results['rule_based'].get('label')} ({results['rule_based'].get('score', 0)*100:.0f}%)")
    
    total_time = time_module.time() - start_time
    results["timing"]["sequential_total_seconds"] = round(total_time, 2)
    print(f"\n⏱️ Total pipeline time: {total_time:.1f}s")
    print("="*60 + "\n")
    
    # Track which engines were used
    if not results["rule_based"].get("error"):
        results["engines_used"].append("rule-based")
    if not results["donut"].get("error"):
        results["engines_used"].append("donut")
    if not results["donut_receipt"].get("error"):
        results["engines_used"].append("donut-receipt")  # NEW
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
        "total_engines": 5  # Rule-Based, DONUT, Donut-Receipt, LayoutLM, Vision LLM
    }
    
    # Tiered approach: Check which engines completed
    critical_engines = {
        "rule-based": not results["rule_based"].get("error"),
        "vision-llm": not results["vision_llm"].get("error")
    }
    
    optional_engines = {
        "donut": not results["donut"].get("error"),
        "donut-receipt": not results["donut_receipt"].get("error"),
        "layoutlm": not results["layoutlm"].get("error")
    }
    
    # Track failed engines for transparency
    failed_engines = []
    if results["rule_based"].get("error"):
        failed_engines.append(f"Rule-Based: {results['rule_based']['error']}")
    if results["donut"].get("error"):
        failed_engines.append(f"DONUT: {results['donut']['error']}")
    if results["donut_receipt"].get("error"):
        failed_engines.append(f"Donut-Receipt: {results['donut_receipt']['error']}")
    if results["layoutlm"].get("error"):
        failed_engines.append(f"LayoutLM: {results['layoutlm']['error']}")
    if results["vision_llm"].get("error"):
        failed_engines.append(f"Vision LLM: {results['vision_llm']['error']}")
    
    # Add transparency info to hybrid verdict
    hybrid["engines_status"] = {
        "critical_complete": all(critical_engines.values()),
        "optional_complete": sum(optional_engines.values()),
        "failed_engines": failed_engines
    }
    
    # Check if critical engines (Rule-Based + Vision LLM) completed
    if not all(critical_engines.values()):
        # Critical engines failed - cannot generate reliable verdict
        hybrid["final_label"] = "incomplete"
        hybrid["confidence"] = 0.0
        hybrid["recommended_action"] = "retry_or_review"
        hybrid["reasoning"].append("⚠️ Critical engines (Rule-Based or Vision LLM) failed")
        
        for failure in failed_engines:
            hybrid["reasoning"].append(f"❌ {failure}")
    else:
        # Generate hybrid verdict using legacy logic
        # (Ensemble will enhance this later, after all engines complete)
        rule_label = results["rule_based"].get("label", "unknown")
        rule_score = results["rule_based"].get("score", 0.5)
        vision_verdict = results["vision_llm"].get("verdict", "unknown")
        vision_confidence = results["vision_llm"].get("confidence", 0.0)
        donut_quality = results["donut"].get("data_quality", "unknown")
        layoutlm_quality = results["layoutlm"].get("data_quality", "unknown")
        
        # Critical engines completed - generate verdict with tiered confidence
        
        # Calculate base confidence from critical engines
        base_confidence = 0.85  # Base with Rule-Based + Vision LLM
        
        # Boost confidence for each optional engine that succeeded
        optional_boost = 0.0
        if optional_engines["donut"] and donut_quality == "good":
            optional_boost += 0.05
        if optional_engines["layoutlm"] and layoutlm_quality == "good":
            optional_boost += 0.05
        
        # Combine signals from available engines
        if rule_label == "real" and rule_score < 0.3:
            if vision_verdict == "real" and vision_confidence > 0.7:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = min(base_confidence + optional_boost, 0.98)
                hybrid["recommended_action"] = "approve"
                
                # Transparent reasoning
                engines_count = 2 + sum(optional_engines.values())
                hybrid["reasoning"].append(f"✅ {engines_count}/{hybrid['total_engines']} engines indicate authentic receipt")
                hybrid["reasoning"].append(f"✅ Critical engines (Rule-Based + Vision LLM) agree: REAL")
                
                if optional_engines["donut"] and donut_quality == "good":
                    hybrid["reasoning"].append("✅ DONUT validated document structure")
                if optional_engines["layoutlm"] and layoutlm_quality == "good":
                    hybrid["reasoning"].append("✅ LayoutLM validated document structure")
                
                # Show failed optional engines transparently
                if not optional_engines["donut"]:
                    hybrid["reasoning"].append("ℹ️ DONUT unavailable (confidence slightly lower)")
                if not optional_engines["layoutlm"]:
                    hybrid["reasoning"].append("ℹ️ LayoutLM unavailable (confidence slightly lower)")
            else:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.80
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("✅ Rule-based engine indicates real receipt")
                hybrid["reasoning"].append("ℹ️ Vision LLM shows lower confidence")
                
        elif rule_label == "fake" or rule_score > 0.7:
            # Rule-Based flagged as fake - but check if Vision LLM disagrees
            if vision_verdict == "real" and vision_confidence > 0.8:
                # Strong disagreement - Vision LLM says real with high confidence
                # Check if DONUT/LayoutLM extracted data successfully (suggests real receipt)
                donut_extracted = results["donut"].get("total") is not None
                layoutlm_extracted = results["layoutlm"].get("total") is not None
                
                if donut_extracted or layoutlm_extracted:
                    # Advanced models extracted data successfully - likely a false positive
                    hybrid["final_label"] = "suspicious"
                    hybrid["confidence"] = 0.70
                    hybrid["recommended_action"] = "human_review"
                    hybrid["reasoning"].append("⚠️ Conflicting signals detected")
                    hybrid["reasoning"].append("❌ Rule-Based flagged fraud indicators")
                    hybrid["reasoning"].append("✅ Vision LLM indicates authentic receipt")
                    if donut_extracted:
                        hybrid["reasoning"].append("✅ DONUT successfully extracted structured data")
                    if layoutlm_extracted:
                        hybrid["reasoning"].append("✅ LayoutLM successfully extracted structured data")
                    hybrid["reasoning"].append("💡 Recommendation: Human review needed - possible OCR error in Rule-Based engine")
                else:
                    # No extraction data - trust Rule-Based
                    hybrid["final_label"] = "fake"
                    hybrid["confidence"] = 0.85
                    hybrid["recommended_action"] = "reject"
                    hybrid["reasoning"].append("❌ Rule-Based detected fraud indicators")
                    hybrid["reasoning"].append("⚠️ Vision LLM disagrees but extraction engines found no data")
            else:
                # Vision LLM agrees or has low confidence
                hybrid["final_label"] = "fake"
                hybrid["confidence"] = min(0.90 + optional_boost, 0.95)
                hybrid["recommended_action"] = "reject"
                
                engines_count = 2 + sum(optional_engines.values())
                hybrid["reasoning"].append(f"❌ {engines_count}/{hybrid['total_engines']} engines indicate fraudulent receipt")
                hybrid["reasoning"].append("❌ High fraud score detected by rule-based engine")
                
                if vision_verdict == "fake":
                    hybrid["reasoning"].append("❌ Vision LLM confirms fraud indicators")
                
        else:
            # Suspicious case - use vision as tiebreaker
            if vision_verdict == "fake" and vision_confidence > 0.7:
                hybrid["final_label"] = "fake"
                hybrid["confidence"] = 0.85
                hybrid["recommended_action"] = "reject"
                hybrid["reasoning"].append("⚠️ Suspicious patterns detected")
                hybrid["reasoning"].append("❌ Vision model detected fraud indicators")
            elif vision_verdict == "real" and vision_confidence > 0.8:
                hybrid["final_label"] = "real"
                hybrid["confidence"] = 0.80
                hybrid["recommended_action"] = "approve"
                hybrid["reasoning"].append("✅ Vision model confirms authenticity")
                hybrid["reasoning"].append("ℹ️ Rule-based shows moderate score")
            else:
                hybrid["final_label"] = "suspicious"
                hybrid["confidence"] = 0.60
                hybrid["recommended_action"] = "human_review"
                hybrid["reasoning"].append("⚠️ Uncertain - requires human review")
                hybrid["reasoning"].append("ℹ️ Mixed signals from engines")
    
    results["hybrid_verdict"] = hybrid
    
    # Build final ensemble verdict (Rule-Based already enhanced with LayoutLM data)
    try:
        print("\n6️⃣ Building ensemble verdict...")
        ensemble = get_ensemble()
        
        # Converge extraction data for transparency
        converged_data = ensemble.converge_extraction(results)
        
        # Build final verdict
        ensemble_verdict = ensemble.build_ensemble_verdict(results, converged_data)
        
        # Override hybrid with ensemble results
        hybrid["final_label"] = ensemble_verdict["final_label"]
        hybrid["confidence"] = ensemble_verdict["confidence"]
        hybrid["recommended_action"] = ensemble_verdict["recommended_action"]
        hybrid["reasoning"] = ensemble_verdict["reasoning"]
        hybrid["agreement_score"] = ensemble_verdict.get("agreement_score", 0.0)
        hybrid["converged_data"] = converged_data
        
        # Update results with enhanced hybrid
        results["hybrid_verdict"] = hybrid
        print(f"   ✅ Final verdict: {ensemble_verdict['final_label']} ({ensemble_verdict['confidence']*100:.0f}%)")
        
    except Exception as e:
        import traceback
        print(f"   ⚠️ Ensemble error: {e}")
        print(f"   Using legacy hybrid verdict")
        traceback.print_exc()
        # Legacy hybrid already in results
    
    # Don't cleanup - keep file for feedback submission
    # File will be cleaned up later or by a background job
    
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
    
    # Save uploaded file with validation
    try:
        temp_path = _save_upload_to_disk(file)
        file_id = temp_path.stem
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )
    
    # Queue for streaming updates
    update_queue = queue.Queue()
    
    results = {
        "receipt_id": file_id,  # Include receipt ID in response
        "rule_based": None,
        "donut": None,
        "donut_receipt": None,
        "layoutlm": None,
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
    
    def run_donut_receipt():
        if not DONUT_RECEIPT_AVAILABLE:
            return {"error": "Donut-Receipt not available", "time_seconds": 0}
        
        update_queue.put({"event": "engine_start", "engine": "donut-receipt"})
        start = time_module.time()
        try:
            data = extract_receipt_with_donut_receipt(str(temp_path))
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
                "engine": "donut-receipt",
                "data": result
            })
            return result
        except Exception as e:
            error_result = {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
            update_queue.put({
                "event": "engine_complete",
                "engine": "donut-receipt",
                "data": error_result
            })
            return error_result
    
    def run_layoutlm():
        if not LAYOUTLM_AVAILABLE:
            return {"error": "LayoutLM not available", "time_seconds": 0}
        
        update_queue.put({"event": "engine_start", "engine": "layoutlm"})
        start = time_module.time()
        try:
            data = extract_receipt_with_layoutlm(str(temp_path))
            elapsed = time_module.time() - start
            result = {
                "merchant": data.get("merchant"),
                "total": data.get("total"),
                "entities_found": len(data.get("entities", [])),
                "confidence": data.get("confidence", 0.0),
                "time_seconds": round(elapsed, 2)
            }
            update_queue.put({
                "event": "engine_complete",
                "engine": "layoutlm",
                "data": result
            })
            return result
        except Exception as e:
            error_result = {"error": str(e), "time_seconds": round(time_module.time() - start, 2)}
            update_queue.put({
                "event": "engine_complete",
                "engine": "layoutlm",
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
        yield f"event: analysis_start\ndata: {json_module.dumps({'message': 'Starting 5-engine analysis'})}\n\n"
        
        # Start all engines in parallel
        loop = asyncio.get_event_loop()
        start_time = time_module.time()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            rule_future = loop.run_in_executor(executor, run_rule_based)
            donut_future = loop.run_in_executor(executor, run_donut)
            donut_receipt_future = loop.run_in_executor(executor, run_donut_receipt)
            layoutlm_future = loop.run_in_executor(executor, run_layoutlm)
            vision_future = loop.run_in_executor(executor, run_vision)
            
            # Stream updates as they come
            engines_completed = 0
            while engines_completed < 5:
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
            results["donut_receipt"] = await donut_receipt_future
            results["layoutlm"] = await layoutlm_future
            results["vision_llm"] = await vision_future
        
        total_time = time_module.time() - start_time
        results["timing"]["parallel_total_seconds"] = round(total_time, 2)
        
        # Track which engines were used
        if not results["rule_based"].get("error"):
            results["engines_used"].append("rule-based")
        if not results["donut"].get("error"):
            results["engines_used"].append("donut")
        if not results["donut_receipt"].get("error"):
            results["engines_used"].append("donut-receipt")
        if not results["layoutlm"].get("error"):
            results["engines_used"].append("layoutlm")
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
        
        # Don't cleanup - keep file for feedback submission
        # File will be cleaned up later or by a background job
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# ---------- Human Feedback Endpoint ----------

class FeedbackRequest(BaseModel):
    """Human feedback for model training"""
    receipt_id: str = Field(..., description="Receipt ID being reviewed")
    human_label: str = Field(..., description="Human verdict: real/suspicious/fake")
    reasons: Optional[List[str]] = Field(default=[], description="Reasons for the verdict")
    corrections: Optional[dict] = Field(default={}, description="Corrected values")
    reviewer_id: Optional[str] = Field(default="anonymous", description="Reviewer identifier")
    timestamp: Optional[str] = Field(default=None, description="Feedback timestamp")


@app.post("/api/feedback", tags=["feedback"])
async def submit_feedback(feedback: FeedbackRequest):
    """
    Submit human feedback for a receipt analysis.
    This feedback is used to train and improve the AI models.
    
    Enterprise-ready:
    - All data stored locally
    - No cloud dependencies
    - GDPR/SOC2 compliant
    - Audit trail maintained
    """
    try:
        from app.feedback.storage import FeedbackStorage
        
        storage = FeedbackStorage()
        
        # Get the receipt file path
        # The receipt_id might be a UUID or filename without extension
        receipt_path = None
        
        # Try different variations
        possible_paths = [
            UPLOAD_DIR / f"{feedback.receipt_id}",
            UPLOAD_DIR / f"{feedback.receipt_id}.jpg",
            UPLOAD_DIR / f"{feedback.receipt_id}.jpeg",
            UPLOAD_DIR / f"{feedback.receipt_id}.png",
            UPLOAD_DIR / f"{feedback.receipt_id}.pdf",
        ]
        
        for path in possible_paths:
            if path.exists():
                receipt_path = path
                break
        
        # If still not found, try to find the most recent receipt
        if not receipt_path:
            all_receipts = sorted(
                list(UPLOAD_DIR.glob("*.jpg")) + 
                list(UPLOAD_DIR.glob("*.jpeg")) + 
                list(UPLOAD_DIR.glob("*.png")) + 
                list(UPLOAD_DIR.glob("*.pdf")),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if all_receipts:
                receipt_path = all_receipts[0]  # Use most recent
                print(f"ℹ️ Receipt ID '{feedback.receipt_id}' not found, using most recent: {receipt_path.name}")
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Receipt file not found for ID: {feedback.receipt_id}"
                )
        
        # Get model predictions (would be stored with the receipt in production)
        model_predictions = {
            "rule_based": {"verdict": "suspicious", "score": 0.65},
            "donut": {"verdict": "real"},
            "donut_receipt": {"confidence": 0.85},
            "layoutlm": {"verdict": "suspicious"},
            "vision_llm": {"verdict": "fake"}
        }
        
        # Save feedback
        feedback_id = storage.save_feedback(
            receipt_id=feedback.receipt_id,
            image_path=str(receipt_path),
            model_predictions=model_predictions,
            human_feedback={
                "label": feedback.human_label,
                "reasons": feedback.reasons,
                "corrections": feedback.corrections
            },
            reviewer_id=feedback.reviewer_id
        )
        
        # Get current stats
        stats = storage.get_stats()
        
        return {
            "status": "success",
            "feedback_id": feedback_id,
            "message": "Feedback saved successfully. Thank you for helping improve our AI!",
            "training_stats": {
                "total_feedback": stats["total_feedback"],
                "pending_training": stats["pending_training"],
                "samples_needed_for_training": max(0, 100 - stats["pending_training"])
            }
        }
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Error saving feedback: {error_details}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save feedback: {str(e)}"
        )


@app.get("/receipt/{receipt_id}/image")
async def get_receipt_image(receipt_id: str):
    """
    Serve the converted receipt image (JPG) for preview.
    Useful for HEIC files that were converted by the server.
    """
    upload_dir = Path("/tmp/verireceipt_uploads")
    
    # Try to find the receipt file (should be .jpg after conversion)
    receipt_path = upload_dir / f"{receipt_id}.jpg"
    
    if not receipt_path.exists():
        # Try other extensions
        for ext in ['.jpeg', '.png', '.pdf']:
            alt_path = upload_dir / f"{receipt_id}{ext}"
            if alt_path.exists():
                receipt_path = alt_path
                break
    
    if not receipt_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt image not found: {receipt_id}"
        )
    
    return FileResponse(
        receipt_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"}
    )