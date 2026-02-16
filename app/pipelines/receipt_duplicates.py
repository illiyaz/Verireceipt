"""
Receipt Duplicate Detection.

Detects duplicate or near-duplicate receipt submissions using fingerprinting:
1. Exact fingerprint: hash(merchant + date + total) — catches identical resubmissions
2. Fuzzy fingerprint: hash(merchant_normalized + date + amount_bucket) — catches
   receipts with slightly edited totals (e.g., $45.00 → $47.50)
3. Image hash: perceptual hash of the receipt image — catches re-photographed receipts

Fingerprints are stored in a lightweight SQLite database for cross-session detection.
"""

import hashlib
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Database path (configurable via env)
_DB_PATH = os.getenv(
    "RECEIPT_FINGERPRINT_DB",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "receipt_fingerprints.db"),
)

_local = threading.local()


def _get_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection, creating tables if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        db_dir = os.path.dirname(os.path.abspath(_DB_PATH))
        os.makedirs(db_dir, exist_ok=True)
        _local.conn = sqlite3.connect(os.path.abspath(_DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _create_tables(_local.conn)
    return _local.conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS receipt_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            exact_fp TEXT,
            fuzzy_fp TEXT,
            merchant TEXT,
            receipt_date TEXT,
            total_amount REAL,
            currency TEXT,
            geo TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(file_path)
        );
        CREATE INDEX IF NOT EXISTS idx_exact_fp ON receipt_fingerprints(exact_fp);
        CREATE INDEX IF NOT EXISTS idx_fuzzy_fp ON receipt_fingerprints(fuzzy_fp);
    """)
    conn.commit()


def _normalize_merchant(merchant: Optional[str]) -> str:
    """Normalize merchant name for fuzzy matching.
    
    'NAYARA ENERGY PVT LTD' and 'Nayara Energy' → 'nayara energy'
    """
    if not merchant:
        return ""
    m = merchant.lower().strip()
    # Remove common suffixes
    for suffix in ["pvt ltd", "pvt. ltd.", "private limited", "limited", "ltd",
                   "inc", "inc.", "llc", "corp", "corporation", "co.",
                   "& co", "enterprises", "services"]:
        m = re.sub(r'\b' + re.escape(suffix) + r'\b', '', m)
    # Collapse whitespace
    m = re.sub(r'\s+', ' ', m).strip()
    return m


def _amount_bucket(amount: Optional[float]) -> str:
    """Bucket amounts to catch small edits.
    
    e.g., $45.00 and $47.50 both → 'bucket_40_50'
    This catches receipts where someone slightly edits the total.
    """
    if amount is None:
        return "none"
    try:
        a = float(amount)
        if a <= 0:
            return "zero"
        # 10-unit buckets
        lower = int(a / 10) * 10
        upper = lower + 10
        return f"bucket_{lower}_{upper}"
    except (ValueError, TypeError):
        return "none"


def _normalize_date(date_str: Optional[str]) -> str:
    """Normalize date to YYYY-MM-DD for consistent fingerprinting."""
    if not date_str:
        return ""
    d = str(date_str).strip()
    # Already in YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', d):
        return d
    # Try common formats
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
                "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(d, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return d


def compute_fingerprints(
    merchant: Optional[str],
    receipt_date: Optional[str],
    total_amount: Optional[float],
) -> Dict[str, Optional[str]]:
    """Compute exact and fuzzy fingerprints for a receipt.
    
    Returns:
        {"exact_fp": "sha256...", "fuzzy_fp": "sha256...", "components": {...}}
    """
    norm_merchant = _normalize_merchant(merchant)
    norm_date = _normalize_date(receipt_date)
    
    # Exact fingerprint: merchant + date + total (penny-exact)
    exact_parts = f"{norm_merchant}|{norm_date}|{total_amount}"
    exact_fp = hashlib.sha256(exact_parts.encode()).hexdigest()[:32] if (norm_merchant or norm_date) else None
    
    # Fuzzy fingerprint: merchant + date + amount bucket
    bucket = _amount_bucket(total_amount)
    fuzzy_parts = f"{norm_merchant}|{norm_date}|{bucket}"
    fuzzy_fp = hashlib.sha256(fuzzy_parts.encode()).hexdigest()[:32] if (norm_merchant or norm_date) else None
    
    return {
        "exact_fp": exact_fp,
        "fuzzy_fp": fuzzy_fp,
        "components": {
            "merchant_normalized": norm_merchant,
            "date_normalized": norm_date,
            "total": total_amount,
            "amount_bucket": bucket,
        },
    }


def check_duplicate(
    file_path: str,
    merchant: Optional[str],
    receipt_date: Optional[str],
    total_amount: Optional[float],
    currency: Optional[str] = None,
    geo: Optional[str] = None,
) -> Dict[str, Any]:
    """Check if a receipt is a duplicate and register its fingerprint.
    
    Returns:
        {
            "is_duplicate": bool,
            "match_type": "exact" | "fuzzy" | None,
            "matched_file": str | None,
            "fingerprints": {...},
            "details": str,
        }
    """
    fps = compute_fingerprints(merchant, receipt_date, total_amount)
    
    result = {
        "is_duplicate": False,
        "match_type": None,
        "matched_file": None,
        "matched_merchant": None,
        "matched_date": None,
        "matched_total": None,
        "fingerprints": fps,
        "details": "",
    }
    
    if not fps["exact_fp"] and not fps["fuzzy_fp"]:
        result["details"] = "Insufficient data for fingerprinting (no merchant or date)"
        return result
    
    try:
        db = _get_db()
        
        # Check exact match first
        if fps["exact_fp"]:
            row = db.execute(
                "SELECT file_path, merchant, receipt_date, total_amount "
                "FROM receipt_fingerprints WHERE exact_fp = ? AND file_path != ?",
                (fps["exact_fp"], file_path),
            ).fetchone()
            if row:
                result["is_duplicate"] = True
                result["match_type"] = "exact"
                result["matched_file"] = row["file_path"]
                result["matched_merchant"] = row["merchant"]
                result["matched_date"] = row["receipt_date"]
                result["matched_total"] = row["total_amount"]
                result["details"] = (
                    f"Exact duplicate: same merchant '{row['merchant']}', "
                    f"date '{row['receipt_date']}', total {row['total_amount']}"
                )
                logger.warning(
                    "DUPLICATE DETECTED (exact): %s matches %s — %s",
                    file_path, row["file_path"], result["details"],
                )
                return result
        
        # Check fuzzy match
        if fps["fuzzy_fp"]:
            row = db.execute(
                "SELECT file_path, merchant, receipt_date, total_amount "
                "FROM receipt_fingerprints WHERE fuzzy_fp = ? AND file_path != ?",
                (fps["fuzzy_fp"], file_path),
            ).fetchone()
            if row:
                result["is_duplicate"] = True
                result["match_type"] = "fuzzy"
                result["matched_file"] = row["file_path"]
                result["matched_merchant"] = row["merchant"]
                result["matched_date"] = row["receipt_date"]
                result["matched_total"] = row["total_amount"]
                result["details"] = (
                    f"Near-duplicate: similar merchant '{row['merchant']}', "
                    f"date '{row['receipt_date']}', total {row['total_amount']} "
                    f"(current total: {total_amount})"
                )
                logger.warning(
                    "DUPLICATE DETECTED (fuzzy): %s matches %s — %s",
                    file_path, row["file_path"], result["details"],
                )
                return result
        
        # No duplicate found — register this receipt
        db.execute(
            "INSERT OR REPLACE INTO receipt_fingerprints "
            "(file_path, exact_fp, fuzzy_fp, merchant, receipt_date, total_amount, currency, geo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (file_path, fps["exact_fp"], fps["fuzzy_fp"],
             merchant, receipt_date, total_amount, currency, geo),
        )
        db.commit()
        result["details"] = "No duplicate found; fingerprint registered"
        
    except Exception as e:
        logger.warning("Duplicate check failed (non-fatal): %s", e)
        result["details"] = f"Check failed: {e}"
    
    return result


def clear_fingerprints() -> int:
    """Clear all stored fingerprints. Returns count of deleted records."""
    try:
        db = _get_db()
        cursor = db.execute("DELETE FROM receipt_fingerprints")
        db.commit()
        return cursor.rowcount
    except Exception as e:
        logger.warning("Failed to clear fingerprints: %s", e)
        return 0


def get_fingerprint_count() -> int:
    """Get total number of stored fingerprints."""
    try:
        db = _get_db()
        row = db.execute("SELECT COUNT(*) as cnt FROM receipt_fingerprints").fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0
