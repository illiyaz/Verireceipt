# app/repository/receipt_store.py
"""
Repository layer for storing VeriReceipt analyses and feedback.

Goal:
- Give the rest of the code a simple, stable interface:
    - save_analysis(file_path, decision)
    - save_feedback(...)
- Hide whether we use:
    - CSV files (early/dev) OR
    - a real database via SQLAlchemy (SQLite/Postgres)

This makes it easy to:
- Start with CSV logging for quick experiments.
- Move to DB later without touching business logic.
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import asdict

from app.schemas.receipt import ReceiptDecision
from app.utils.logger import log_decision  # CSV-based logger (already implemented)

# If you’ve already created these, they will be used by DbReceiptStore.
# If not, DbReceiptStore will just be a placeholder until Step 2.
try:
    from app.db.base import SessionLocal
    from app.db import models as db_models
    HAS_DB = True
except ImportError:
    # We haven't wired the DB layer yet – CSV mode will still work fine.
    HAS_DB = False


# ---------------------------------------------------------------------------
# 1. Abstract Repository Interface
# ---------------------------------------------------------------------------

class ReceiptStore(ABC):
    """
    Abstract base class for storing analyses and feedback.

    Implementations:
    - CsvReceiptStore: logs to CSV via app.utils.logger.log_decision
    - DbReceiptStore:  writes to SQLAlchemy models (Receipt, Analysis, Feedback)
    """

    @abstractmethod
    def save_analysis(self, file_path: str, decision: ReceiptDecision) -> Any:
        """
        Persist an engine decision for a given receipt file.

        Returns:
            A backend-specific identifier (e.g., analysis_id for DB,
            or filename/None for CSV).
        """
        raise NotImplementedError

    @abstractmethod
    def save_feedback(
        self,
        receipt_identifier: Any,
        analysis_identifier: Any,
        given_label: str,
        reviewer_id: Optional[str] = None,
        comment: Optional[str] = None,
        reason_code: Optional[str] = None,
    ) -> Any:
        """
        Persist human feedback/override for an analysis.

        For CSV backend, this might append to a separate feedback CSV.
        For DB backend, this will insert into a Feedback table.

        Returns:
            A backend-specific identifier for the feedback entry.
        """
        raise NotImplementedError

    @abstractmethod
    def get_statistics(self) -> dict:
        """
        Get aggregate statistics about all analyzed receipts.

        Returns:
            Dictionary with keys: total_analyses, real_count, suspicious_count,
            fake_count, avg_score
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 2. CSV Implementation (using existing decisions.csv logger)
# ---------------------------------------------------------------------------

class CsvReceiptStore(ReceiptStore):
    """
    ReceiptStore implementation that logs analyses to CSV.

    - Uses existing log_decision(file_path, decision) for analyses.
    - Feedback can be logged to a separate feedback CSV (to be added).
    """

    def __init__(self, decisions_log_path: Optional[str] = None):
        # Allow overriding log file path; default to app.utils.logger.LOG_FILE
        self.decisions_log_path = decisions_log_path  # currently unused; log_decision handles its own path

    def save_analysis(self, file_path: str, decision: ReceiptDecision) -> Any:
        """
        Append analysis to decisions CSV.

        Returns:
            For CSV backend we don't have a strict numeric ID,
            so we simply return the filename as a convenient identifier.
        """
        log_decision(file_path, decision)
        # In CSV mode, we don't have an analysis_id; callers can use filename or None.
        return os.path.basename(file_path)

    def save_feedback(
        self,
        receipt_identifier: Any,
        analysis_identifier: Any,
        given_label: str,
        reviewer_id: Optional[str] = None,
        comment: Optional[str] = None,
        reason_code: Optional[str] = None,
    ) -> Any:
        """
        Log human feedback to CSV for later ML training.
        
        Feedback is saved to data/logs/feedback.csv with:
        - Original engine prediction
        - Human-corrected label
        - Reviewer information
        - Comments and reason codes
        """
        from app.utils.feedback_logger import log_feedback
        
        # Try to get original engine prediction from decisions.csv
        engine_label = None
        engine_score = None
        
        try:
            import csv
            from pathlib import Path
            
            decisions_file = Path("data/logs/decisions.csv")
            if decisions_file.exists():
                with open(decisions_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("file_path") == str(analysis_identifier):
                            engine_label = row.get("label")
                            engine_score = float(row.get("score", 0.0))
                            break
        except Exception:
            pass
        
        timestamp = log_feedback(
            analysis_ref=str(analysis_identifier),
            given_label=given_label,
            engine_label=engine_label,
            engine_score=engine_score,
            receipt_ref=str(receipt_identifier) if receipt_identifier else None,
            reviewer_id=reviewer_id,
            comment=comment,
            reason_code=reason_code,
        )
        
        return timestamp

    def get_statistics(self) -> dict:
        """
        Read decisions.csv and compute aggregate statistics.
        """
        import csv
        from pathlib import Path

        log_file = Path("data/logs/decisions.csv")
        if not log_file.exists():
            return {
                "total_analyses": 0,
                "real_count": 0,
                "suspicious_count": 0,
                "fake_count": 0,
                "avg_score": 0.0,
            }

        real_count = 0
        suspicious_count = 0
        fake_count = 0
        total_score = 0.0
        total_analyses = 0

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_analyses += 1
                    label = row.get("label", "").lower()
                    score = float(row.get("score", 0.0))

                    if label == "real":
                        real_count += 1
                    elif label == "suspicious":
                        suspicious_count += 1
                    elif label == "fake":
                        fake_count += 1

                    total_score += score
        except Exception:
            # If CSV is malformed, return zeros
            pass

        avg_score = total_score / total_analyses if total_analyses > 0 else 0.0

        return {
            "total_analyses": total_analyses,
            "real_count": real_count,
            "suspicious_count": suspicious_count,
            "fake_count": fake_count,
            "avg_score": avg_score,
        }


# ---------------------------------------------------------------------------
# 3. DB Implementation (using SQLAlchemy models)
# ---------------------------------------------------------------------------

class DbReceiptStore(ReceiptStore):
    """
    ReceiptStore implementation backed by a relational DB via SQLAlchemy.

    Requires:
        - app.db.base.SessionLocal
        - app.db.models with Receipt, Analysis, Feedback models.

    This class encapsulates:
        - Creating/finding the Receipt row for a given file.
        - Inserting an Analysis row for each engine decision.
        - Inserting Feedback rows when humans override.
    """

    def __init__(self):
        if not HAS_DB:
            raise RuntimeError(
                "Database dependencies are not available. "
                "Ensure app.db.base and app.db.models exist and are importable."
            )

    def _get_or_create_receipt(self, session, file_path: str, decision: ReceiptDecision) -> Any:
        """
        Find an existing Receipt row by file_name (or file_hash later),
        or create a new one if it doesn't exist.

        NOTE:
        - For a production system you should dedupe using file_hash (e.g. sha256).
        - For now we keep it simple and use file_name.
        """
        file_name = os.path.basename(file_path)
        source_type = decision.features.file_features.get("source_type") if decision.features else None
        file_size_bytes = decision.features.file_features.get("file_size_bytes") if decision.features else None

        receipt = (
            session.query(db_models.Receipt)
            .filter(db_models.Receipt.file_name == file_name)
            .order_by(db_models.Receipt.id.desc())
            .first()
        )
        if receipt is None:
            receipt = db_models.Receipt(
                file_name=file_name,
                source_type=source_type,
                file_size_bytes=file_size_bytes,
            )
            session.add(receipt)
            session.flush()  # assign receipt.id
        return receipt

    def save_analysis(self, file_path: str, decision: ReceiptDecision) -> Any:
        """
        Persist an Analysis row for this decision and return the analysis_id.
        """
        session = SessionLocal()
        try:
            # 1. Ensure we have a Receipt row
            receipt = self._get_or_create_receipt(session, file_path, decision)

            # 2. Build Analysis row
            features = decision.features
            
            # Serialize audit_events and events to JSON
            audit_events_json = json.dumps([asdict(e) for e in decision.audit_events]) if decision.audit_events else None
            events_json = json.dumps(decision.events) if decision.events else None
            
            analysis = db_models.Analysis(
                receipt_id=receipt.id,
                engine_label=decision.label,
                engine_score=decision.score,
                engine_version=decision.engine_version or "rules-v1.0",
                rule_version=decision.rule_version,
                policy_version=decision.policy_version,
                policy_name=decision.policy_name,
                decision_id=decision.decision_id,
                created_at=decision.created_at,
                finalized=decision.finalized,
                policy_notes=decision.policy_notes,
                extraction_confidence_score=decision.extraction_confidence_score,
                extraction_confidence_level=decision.extraction_confidence_level,
                normalized_total=decision.normalized_total,
                currency=decision.currency,
                reasons=decision.reasons,
                minor_notes=decision.minor_notes,
                audit_events=audit_events_json,
                events=events_json,
                features={
                    # Store all features as one JSON dict for ML.
                    **(features.file_features if features else {}),
                    **(features.text_features if features else {}),
                    **(features.layout_features if features else {}),
                    **(features.forensic_features if features else {}),
                } if features is not None else None,
            )

            session.add(analysis)
            session.commit()
            session.refresh(analysis)

            return analysis.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_feedback(
        self,
        receipt_identifier: Any,
        analysis_identifier: Any,
        given_label: str,
        reviewer_id: Optional[str] = None,
        comment: Optional[str] = None,
        reason_code: Optional[str] = None,
    ) -> Any:
        """
        Persist a Feedback row linked to a specific analysis/receipt.

        - receipt_identifier: typically the receipt_id (int)
        - analysis_identifier: the analysis_id (int)
        """
        session = SessionLocal()
        try:
            feedback = db_models.Feedback(
                receipt_id=receipt_identifier,
                analysis_id=analysis_identifier,
                given_label=given_label,
                reviewer_id=reviewer_id,
                comment=comment,
                reason_code=reason_code,
                is_override=True,
            )
            session.add(feedback)
            session.commit()
            session.refresh(feedback)
            return feedback.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_statistics(self) -> dict:
        """
        Get aggregate statistics from the Analysis table.
        """
        from sqlalchemy import func

        session = SessionLocal()
        try:
            total_analyses = session.query(func.count(db_models.Analysis.id)).scalar() or 0
            
            real_count = (
                session.query(func.count(db_models.Analysis.id))
                .filter(db_models.Analysis.engine_label == "real")
                .scalar() or 0
            )
            
            suspicious_count = (
                session.query(func.count(db_models.Analysis.id))
                .filter(db_models.Analysis.engine_label == "suspicious")
                .scalar() or 0
            )
            
            fake_count = (
                session.query(func.count(db_models.Analysis.id))
                .filter(db_models.Analysis.engine_label == "fake")
                .scalar() or 0
            )
            
            avg_score = session.query(func.avg(db_models.Analysis.engine_score)).scalar() or 0.0

            return {
                "total_analyses": total_analyses,
                "real_count": real_count,
                "suspicious_count": suspicious_count,
                "fake_count": fake_count,
                "avg_score": float(avg_score),
            }
        finally:
            session.close()


# ---------------------------------------------------------------------------
# 4. Factory: choose backend via env var
# ---------------------------------------------------------------------------

def get_receipt_store() -> ReceiptStore:
    """
    Factory to obtain a ReceiptStore implementation.

    Controlled by env var:
        VERIRECEIPT_STORE_BACKEND = "db" | "csv"

    Defaults to:
        - "db" if DB is available and env var is set to "db"
        - otherwise "csv"
    """
    backend = os.getenv("VERIRECEIPT_STORE_BACKEND", "").lower()

    if backend == "db" and HAS_DB:
        return DbReceiptStore()

    # Fallback to CSV for simplicity during development
    return CsvReceiptStore()