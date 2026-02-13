"""
Feedback storage with dual-mode: PostgreSQL (Render) or SQLite (local dev).

Set DATABASE_URL env var for PostgreSQL, otherwise falls back to SQLite.
"""

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from app.models.feedback import (
    ReceiptFeedback,
    FeedbackStats,
    LearningRule,
    FeedbackType,
    CorrectVerdict
)

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(_DATABASE_URL and "postgres" in _DATABASE_URL)
_pg_pool = None

def _get_pg_pool():
    """Lazy-init PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None:
        import psycopg2
        from psycopg2 import pool
        from psycopg2.extras import RealDictCursor
        # Render uses postgres:// but psycopg2 needs postgresql://
        db_url = _DATABASE_URL.replace("postgres://", "postgresql://", 1)
        _pg_pool = pool.ThreadedConnectionPool(1, 3, db_url)
        print("✅ Feedback PostgreSQL connection pool created")
    return _pg_pool

class FeedbackStore:
    """
    Feedback and learned-rules storage.

    Dual-mode:
    - PostgreSQL when DATABASE_URL is set (Render / production)
    - SQLite fallback for local development
    """

    def __init__(self, db_path: str = "data/feedback.db"):
        """Initialize feedback store."""
        self.use_pg = USE_POSTGRES
        if not self.use_pg:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        if self.use_pg:
            from psycopg2.extras import RealDictCursor
            conn = _get_pg_pool().getconn()
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                _get_pg_pool().putconn(conn)
        else:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    def _cursor(self, conn):
        """Get a cursor appropriate for the backend."""
        if self.use_pg:
            from psycopg2.extras import RealDictCursor
            return conn.cursor(cursor_factory=RealDictCursor)
        return conn.cursor()

    def _sql(self, query: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s."""
        if self.use_pg:
            return query.replace("?", "%s")
        return query

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)

            if self.use_pg:
                self._init_pg(cursor)
            else:
                self._init_sqlite(cursor)

    def _init_sqlite(self, cursor):
        """SQLite schema."""
        # Feedback table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                receipt_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Original analysis
                system_verdict TEXT NOT NULL,
                system_confidence REAL NOT NULL,
                system_reasoning TEXT,  -- JSON array

                -- User correction
                correct_verdict TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                user_notes TEXT,

                -- Context
                engines_used TEXT,  -- JSON array
                rule_based_score REAL,
                vision_llm_verdict TEXT,

                -- Indicators
                detected_indicators TEXT,  -- JSON array
                missed_indicators TEXT,  -- JSON array
                false_indicators TEXT,  -- JSON array

                -- Learning data (anonymized)
                merchant_pattern TEXT,
                software_detected TEXT,
                has_date_issue BOOLEAN,
                has_spacing_issue BOOLEAN,

                -- Metadata
                user_id TEXT,
                session_id TEXT
            )
        """)

        # Learned rules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_rules (
                rule_id TEXT PRIMARY KEY,
                rule_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence_adjustment REAL DEFAULT 0.0,

                -- Learning metadata
                learned_from_feedback_count INTEGER DEFAULT 1,
                accuracy_on_validation REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Status
                enabled BOOLEAN DEFAULT 1,
                auto_learned BOOLEAN DEFAULT 1
            )
        """)

        # Accuracy tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_metrics (
                metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_feedback INTEGER,
                correct_verdicts INTEGER,
                false_positives INTEGER,
                false_negatives INTEGER,
                accuracy REAL
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON feedback(correct_verdict)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_type ON learned_rules(rule_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_enabled ON learned_rules(enabled)")

    def _init_pg(self, cursor):
        """PostgreSQL schema."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                receipt_id TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                system_verdict TEXT NOT NULL,
                system_confidence DOUBLE PRECISION NOT NULL,
                system_reasoning TEXT,
                correct_verdict TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                user_notes TEXT,
                engines_used TEXT,
                rule_based_score DOUBLE PRECISION,
                vision_llm_verdict TEXT,
                detected_indicators TEXT,
                missed_indicators TEXT,
                false_indicators TEXT,
                merchant_pattern TEXT,
                software_detected TEXT,
                has_date_issue BOOLEAN DEFAULT FALSE,
                has_spacing_issue BOOLEAN DEFAULT FALSE,
                user_id TEXT,
                session_id TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_rules (
                rule_id TEXT PRIMARY KEY,
                rule_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence_adjustment DOUBLE PRECISION DEFAULT 0.0,
                learned_from_feedback_count INTEGER DEFAULT 1,
                accuracy_on_validation DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT NOW(),
                last_updated TIMESTAMP DEFAULT NOW(),
                enabled BOOLEAN DEFAULT TRUE,
                auto_learned BOOLEAN DEFAULT TRUE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_metrics (
                metric_id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT NOW(),
                total_feedback INTEGER,
                correct_verdicts INTEGER,
                false_positives INTEGER,
                false_negatives INTEGER,
                accuracy DOUBLE PRECISION
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON feedback(correct_verdict)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_type ON learned_rules(rule_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_enabled ON learned_rules(enabled)")

    def save_feedback(self, feedback: ReceiptFeedback) -> str:
        """Save user feedback."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)
            params = (
                feedback.feedback_id,
                feedback.receipt_id,
                feedback.created_at,
                feedback.system_verdict,
                feedback.system_confidence,
                json.dumps(feedback.system_reasoning),
                feedback.correct_verdict.value,
                feedback.feedback_type.value,
                feedback.user_notes,
                json.dumps(feedback.engines_used),
                feedback.rule_based_score,
                feedback.vision_llm_verdict,
                json.dumps(feedback.detected_indicators),
                json.dumps(feedback.missed_indicators),
                json.dumps(feedback.false_indicators),
                feedback.merchant_pattern,
                feedback.software_detected,
                feedback.has_date_issue,
                feedback.has_spacing_issue,
                feedback.user_id,
                feedback.session_id
            )

            if self.use_pg:
                cursor.execute("""
                    INSERT INTO feedback (
                        feedback_id, receipt_id, created_at,
                        system_verdict, system_confidence, system_reasoning,
                        correct_verdict, feedback_type, user_notes,
                        engines_used, rule_based_score, vision_llm_verdict,
                        detected_indicators, missed_indicators, false_indicators,
                        merchant_pattern, software_detected, has_date_issue, has_spacing_issue,
                        user_id, session_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (feedback_id) DO NOTHING
                """, params)
            else:
                cursor.execute("""
                    INSERT INTO feedback (
                        feedback_id, receipt_id, created_at,
                        system_verdict, system_confidence, system_reasoning,
                        correct_verdict, feedback_type, user_notes,
                        engines_used, rule_based_score, vision_llm_verdict,
                        detected_indicators, missed_indicators, false_indicators,
                        merchant_pattern, software_detected, has_date_issue, has_spacing_issue,
                        user_id, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, params)
            
            return feedback.feedback_id
    
    def get_feedback(self, feedback_id: str) -> Optional[ReceiptFeedback]:
        """Get feedback by ID."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)
            cursor.execute(self._sql("SELECT * FROM feedback WHERE feedback_id = ?"), (feedback_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return self._row_to_feedback(row)
    
    def get_all_feedback(self, limit: int = 100, offset: int = 0) -> List[ReceiptFeedback]:
        """Get all feedback with pagination."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)
            cursor.execute(
                self._sql("SELECT * FROM feedback ORDER BY created_at DESC LIMIT ? OFFSET ?"),
                (limit, offset)
            )
            rows = cursor.fetchall()
            
            return [self._row_to_feedback(row) for row in rows]
    
    def get_stats(self, days: int = 30) -> FeedbackStats:
        """Get feedback statistics."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)
            
            # Get counts - use backend-appropriate date math
            if self.use_pg:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN system_verdict = correct_verdict THEN 1 ELSE 0 END) as correct,
                        SUM(CASE WHEN feedback_type = 'false_positive' THEN 1 ELSE 0 END) as fp,
                        SUM(CASE WHEN feedback_type = 'false_negative' THEN 1 ELSE 0 END) as fn,
                        SUM(CASE WHEN correct_verdict = 'real' THEN 1 ELSE 0 END) as real,
                        SUM(CASE WHEN correct_verdict = 'fake' THEN 1 ELSE 0 END) as fake,
                        SUM(CASE WHEN correct_verdict = 'suspicious' THEN 1 ELSE 0 END) as suspicious
                    FROM feedback
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                """, (days,))
            else:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN system_verdict = correct_verdict THEN 1 ELSE 0 END) as correct,
                        SUM(CASE WHEN feedback_type = 'false_positive' THEN 1 ELSE 0 END) as fp,
                        SUM(CASE WHEN feedback_type = 'false_negative' THEN 1 ELSE 0 END) as fn,
                        SUM(CASE WHEN correct_verdict = 'real' THEN 1 ELSE 0 END) as real,
                        SUM(CASE WHEN correct_verdict = 'fake' THEN 1 ELSE 0 END) as fake,
                        SUM(CASE WHEN correct_verdict = 'suspicious' THEN 1 ELSE 0 END) as suspicious
                    FROM feedback
                    WHERE created_at >= datetime('now', '-' || ? || ' days')
                """, (days,))
            
            row = cursor.fetchone()
            
            total = row['total'] or 0
            correct = row['correct'] or 0
            accuracy = (correct / total * 100) if total > 0 else 0.0
            
            # Get common missed indicators
            if self.use_pg:
                cursor.execute("""
                    SELECT missed_indicators
                    FROM feedback
                    WHERE missed_indicators != '[]'
                    AND created_at >= NOW() - INTERVAL '%s days'
                """, (days,))
            else:
                cursor.execute("""
                    SELECT missed_indicators
                    FROM feedback
                    WHERE missed_indicators != '[]'
                    AND created_at >= datetime('now', '-' || ? || ' days')
                """, (days,))
            
            missed_indicators = []
            for r in cursor.fetchall():
                val = r['missed_indicators'] if isinstance(r, dict) else r[0]
                indicators = json.loads(val)
                missed_indicators.extend(indicators)
            
            # Count occurrences
            from collections import Counter
            missed_counts = Counter(missed_indicators)
            most_common_missed = [
                {"indicator": ind, "count": count}
                for ind, count in missed_counts.most_common(5)
            ]
            
            return FeedbackStats(
                total_feedback=total,
                correct_verdicts=correct,
                false_positives=row['fp'] or 0,
                false_negatives=row['fn'] or 0,
                accuracy=round(accuracy, 2),
                real_receipts=row['real'] or 0,
                fake_receipts=row['fake'] or 0,
                suspicious_receipts=row['suspicious'] or 0,
                most_common_missed_indicators=most_common_missed
            )
    
    def save_learned_rule(self, rule: LearningRule) -> str:
        """Save a learned rule."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)
            params = (
                rule.rule_id,
                rule.rule_type,
                rule.pattern,
                rule.action,
                rule.confidence_adjustment,
                rule.learned_from_feedback_count,
                rule.accuracy_on_validation,
                rule.created_at,
                rule.last_updated,
                rule.enabled,
                rule.auto_learned
            )

            if self.use_pg:
                cursor.execute("""
                    INSERT INTO learned_rules (
                        rule_id, rule_type, pattern, action, confidence_adjustment,
                        learned_from_feedback_count, accuracy_on_validation,
                        created_at, last_updated, enabled, auto_learned
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (rule_id) DO UPDATE SET
                        rule_type=EXCLUDED.rule_type, pattern=EXCLUDED.pattern,
                        action=EXCLUDED.action, confidence_adjustment=EXCLUDED.confidence_adjustment,
                        learned_from_feedback_count=EXCLUDED.learned_from_feedback_count,
                        accuracy_on_validation=EXCLUDED.accuracy_on_validation,
                        last_updated=EXCLUDED.last_updated, enabled=EXCLUDED.enabled,
                        auto_learned=EXCLUDED.auto_learned
                """, params)
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO learned_rules (
                        rule_id, rule_type, pattern, action, confidence_adjustment,
                        learned_from_feedback_count, accuracy_on_validation,
                        created_at, last_updated, enabled, auto_learned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, params)
            
            return rule.rule_id
    
    def get_learned_rules(self, enabled_only: bool = True) -> List[LearningRule]:
        """Get all learned rules."""
        with self._get_connection() as conn:
            cursor = self._cursor(conn)
            
            query = "SELECT * FROM learned_rules"
            if enabled_only:
                if self.use_pg:
                    query += " WHERE enabled = TRUE"
                else:
                    query += " WHERE enabled = 1"
            query += " ORDER BY accuracy_on_validation DESC"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            return [self._row_to_rule(row) for row in rows]
    
    def _row_to_feedback(self, row) -> ReceiptFeedback:
        """Convert database row to ReceiptFeedback."""
        ca = row['created_at']
        created_at = ca if isinstance(ca, datetime) else datetime.fromisoformat(str(ca))
        return ReceiptFeedback(
            feedback_id=row['feedback_id'],
            receipt_id=row['receipt_id'],
            created_at=created_at,
            system_verdict=row['system_verdict'],
            system_confidence=row['system_confidence'],
            system_reasoning=json.loads(row['system_reasoning'] or '[]'),
            correct_verdict=CorrectVerdict(row['correct_verdict']),
            feedback_type=FeedbackType(row['feedback_type']),
            user_notes=row['user_notes'],
            engines_used=json.loads(row['engines_used'] or '[]'),
            rule_based_score=row['rule_based_score'],
            vision_llm_verdict=row['vision_llm_verdict'],
            detected_indicators=json.loads(row['detected_indicators'] or '[]'),
            missed_indicators=json.loads(row['missed_indicators'] or '[]'),
            false_indicators=json.loads(row['false_indicators'] or '[]'),
            merchant_pattern=row['merchant_pattern'],
            software_detected=row['software_detected'],
            has_date_issue=bool(row['has_date_issue']),
            has_spacing_issue=bool(row['has_spacing_issue']),
            user_id=row['user_id'],
            session_id=row['session_id']
        )
    
    def _row_to_rule(self, row) -> LearningRule:
        """Convert database row to LearningRule."""
        ca = row['created_at']
        lu = row['last_updated']
        created_at = ca if isinstance(ca, datetime) else datetime.fromisoformat(str(ca))
        last_updated = lu if isinstance(lu, datetime) else datetime.fromisoformat(str(lu))
        return LearningRule(
            rule_id=row['rule_id'],
            rule_type=row['rule_type'],
            pattern=row['pattern'],
            action=row['action'],
            confidence_adjustment=row['confidence_adjustment'],
            learned_from_feedback_count=row['learned_from_feedback_count'],
            accuracy_on_validation=row['accuracy_on_validation'],
            created_at=created_at,
            last_updated=last_updated,
            enabled=bool(row['enabled']),
            auto_learned=bool(row['auto_learned'])
        )


# Global feedback store instance
_feedback_store: Optional[FeedbackStore] = None


def get_feedback_store() -> FeedbackStore:
    """Get or create global feedback store instance."""
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore()
    return _feedback_store
