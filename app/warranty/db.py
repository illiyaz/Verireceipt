"""Database operations for warranty claims.

Dual-mode: PostgreSQL (production/Render) or SQLite (local dev).
Set DATABASE_URL env var for PostgreSQL, otherwise falls back to SQLite.
"""

import os
import sqlite3
import json
import threading
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

from .bootstrap import get_warranty_db_path, bootstrap_warranty_db, bootstrap_warranty_db_pg


_local = threading.local()

# Detect database mode from environment
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

# PostgreSQL connection pool (lazy init)
_pg_pool = None


def _get_pg_pool():
    """Get or create PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None:
        import psycopg2
        from psycopg2 import pool as pg_pool
        # Render uses postgres:// but psycopg2 needs postgresql://
        db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        _pg_pool = pg_pool.ThreadedConnectionPool(1, 3, db_url)
        # Bootstrap schema on first connect
        conn = _pg_pool.getconn()
        try:
            bootstrap_warranty_db_pg(conn)
            conn.commit()
        finally:
            _pg_pool.putconn(conn)
        print(f"\u2705 PostgreSQL connection pool created")
    return _pg_pool


def get_connection():
    """Get database connection. PostgreSQL if DATABASE_URL set, else SQLite."""
    if USE_POSTGRES:
        return _get_pg_pool().getconn()
    else:
        if not hasattr(_local, "conn") or _local.conn is None:
            db_path = get_warranty_db_path()
            if not Path(db_path).exists():
                bootstrap_warranty_db(db_path)
            _local.conn = sqlite3.connect(db_path, check_same_thread=False)
            _local.conn.row_factory = sqlite3.Row
        return _local.conn


def release_connection(conn):
    """Release connection back to pool (PostgreSQL only). No-op for SQLite."""
    if USE_POSTGRES and _pg_pool is not None:
        _pg_pool.putconn(conn)


def _sql(query: str) -> str:
    """Convert SQLite-style ? placeholders to PostgreSQL %s if needed."""
    if USE_POSTGRES:
        return query.replace("?", "%s")
    return query


def _get_cursor(conn):
    """Get a cursor with dict-like rows."""
    if USE_POSTGRES:
        from psycopg2.extras import RealDictCursor
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()


def save_claim(claim_data: Dict[str, Any]) -> str:
    """Save a warranty claim to the database."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        now = datetime.now().isoformat()

        params = (
            claim_data.get("claim_id"),
            claim_data.get("customer_name"),
            claim_data.get("dealer_id"),
            claim_data.get("dealer_name"),
            claim_data.get("vin"),
            claim_data.get("brand"),
            claim_data.get("model"),
            claim_data.get("year"),
            claim_data.get("odometer"),
            claim_data.get("issue_description"),
            claim_data.get("claim_date"),
            claim_data.get("decision_date"),
            claim_data.get("parts_cost"),
            claim_data.get("labor_cost"),
            claim_data.get("tax"),
            claim_data.get("total_amount"),
            claim_data.get("status"),
            claim_data.get("rejection_reason"),
            claim_data.get("risk_score"),
            claim_data.get("triage_class"),
            json.dumps(claim_data.get("fraud_signals", [])),
            json.dumps(claim_data.get("warnings", [])),
            1 if claim_data.get("is_suspicious") else 0,
            claim_data.get("pdf_path"),
            claim_data.get("raw_text"),
            now,
            now
        )

        _columns = """(id, customer_name, dealer_id, dealer_name,
         vin, brand, model, year, odometer,
         issue_description, claim_date, decision_date,
         parts_cost, labor_cost, tax, total_amount,
         status, rejection_reason,
         risk_score, triage_class, fraud_signals, warnings, is_suspicious,
         pdf_path, raw_text, created_at, updated_at)"""

        if USE_POSTGRES:
            cursor.execute(f"""
                INSERT INTO warranty_claims {_columns}
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    customer_name=EXCLUDED.customer_name, dealer_id=EXCLUDED.dealer_id,
                    dealer_name=EXCLUDED.dealer_name, vin=EXCLUDED.vin, brand=EXCLUDED.brand,
                    model=EXCLUDED.model, year=EXCLUDED.year, odometer=EXCLUDED.odometer,
                    issue_description=EXCLUDED.issue_description, claim_date=EXCLUDED.claim_date,
                    decision_date=EXCLUDED.decision_date, parts_cost=EXCLUDED.parts_cost,
                    labor_cost=EXCLUDED.labor_cost, tax=EXCLUDED.tax, total_amount=EXCLUDED.total_amount,
                    status=EXCLUDED.status, rejection_reason=EXCLUDED.rejection_reason,
                    risk_score=EXCLUDED.risk_score, triage_class=EXCLUDED.triage_class,
                    fraud_signals=EXCLUDED.fraud_signals, warnings=EXCLUDED.warnings,
                    is_suspicious=EXCLUDED.is_suspicious, pdf_path=EXCLUDED.pdf_path,
                    raw_text=EXCLUDED.raw_text, updated_at=EXCLUDED.updated_at
            """, params)
        else:
            cursor.execute(f"""
                INSERT OR REPLACE INTO warranty_claims {_columns}
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, params)

        conn.commit()
        return claim_data.get("claim_id")
    finally:
        release_connection(conn)


def get_claim(claim_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a warranty claim by ID."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute(_sql("SELECT * FROM warranty_claims WHERE id = ?"), (claim_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        release_connection(conn)


def claim_exists(claim_id: str) -> bool:
    """Check if a claim already exists."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute(_sql("SELECT 1 FROM warranty_claims WHERE id = ?"), (claim_id,))
        return cursor.fetchone() is not None
    finally:
        release_connection(conn)


def delete_claim_images(claim_id: str) -> int:
    """Delete all image fingerprints and duplicate matches for a claim (used on re-analysis)."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        # Delete duplicate matches first (FK references)
        cursor.execute(_sql(
            "DELETE FROM warranty_duplicate_matches WHERE claim_id_1 = ? OR claim_id_2 = ?"
        ), (claim_id, claim_id))
        # Delete image fingerprints
        cursor.execute(_sql(
            "DELETE FROM warranty_claim_images WHERE claim_id = ?"
        ), (claim_id,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    finally:
        release_connection(conn)


def save_image_fingerprint(
    claim_id: str,
    image_index: int,
    phash: str,
    dhash: Optional[str] = None,
    file_hash: Optional[str] = None,
    exif_data: Optional[Dict] = None,
    dimensions: Optional[Tuple[int, int]] = None,
    extraction_method: str = "embedded",
    page_number: int = 0,
    bbox: Optional[tuple] = None
) -> int:
    """Save image fingerprint for duplicate detection."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        exif_data = exif_data or {}

        params = (
            claim_id, image_index, phash, dhash, file_hash,
            exif_data.get("timestamp"), exif_data.get("gps_lat"),
            exif_data.get("gps_lon"), exif_data.get("device"),
            exif_data.get("software"),
            dimensions[0] if dimensions else None,
            dimensions[1] if dimensions else None,
            extraction_method, page_number,
            json.dumps(bbox) if bbox else None
        )

        base_sql = """INSERT INTO warranty_claim_images 
            (claim_id, image_index, phash, dhash, file_hash,
             exif_timestamp, exif_gps_lat, exif_gps_lon, exif_device, exif_software,
             width, height, extraction_method, page_number, bbox)"""

        if USE_POSTGRES:
            cursor.execute(f"""{base_sql}
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, params)
            row_id = cursor.fetchone()["id"]
        else:
            cursor.execute(f"""{base_sql}
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, params)
            row_id = cursor.lastrowid

        conn.commit()
        return row_id
    finally:
        release_connection(conn)


def find_similar_images(
    phash: str,
    exclude_claim_id: Optional[str] = None,
    max_hamming_distance: int = 10
) -> List[Dict[str, Any]]:
    """
    Find images with similar perceptual hash.
    
    Uses Hamming distance to find near-duplicates.
    Hamming distance of 0 = exact match
    Hamming distance < 10 = likely same image
    
    Excludes template-like images (banners, headers) based on aspect ratio.
    """
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        _float = "DOUBLE PRECISION" if USE_POSTGRES else "REAL"

        # Get all image hashes, excluding template-like images (banners/headers)
        # Filter: aspect ratio <= 5:1, dimensions >= 200px
        if exclude_claim_id:
            cursor.execute(_sql(f"""
                SELECT id, claim_id, image_index, phash, dhash, 
                       exif_timestamp, exif_device, width, height
                FROM warranty_claim_images 
                WHERE claim_id != ?
                  AND width > 0 AND height > 0
                  AND (CAST(width AS {_float}) / height) <= 5.0
                  AND (CAST(height AS {_float}) / width) <= 5.0
                  AND height >= 200 AND width >= 200
            """), (exclude_claim_id,))
        else:
            cursor.execute(f"""
                SELECT id, claim_id, image_index, phash, dhash,
                       exif_timestamp, exif_device, width, height
                FROM warranty_claim_images
                WHERE width > 0 AND height > 0
                  AND (CAST(width AS {_float}) / height) <= 5.0
                  AND (CAST(height AS {_float}) / width) <= 5.0
                  AND height >= 200 AND width >= 200
            """)

        matches = []
        for row in cursor.fetchall():
            stored_phash = row["phash"]
            distance = _hamming_distance(phash, stored_phash)

            if distance <= max_hamming_distance:
                matches.append({
                    "id": row["id"],
                    "claim_id": row["claim_id"],
                    "image_index": row["image_index"],
                    "phash": stored_phash,
                    "hamming_distance": distance,
                    "similarity_score": 1.0 - (distance / 64.0),  # 64-bit hash
                    "exif_timestamp": row["exif_timestamp"],
                    "exif_device": row["exif_device"],
                    "dimensions": (row["width"], row["height"])
                })

        # Sort by similarity (closest first)
        matches.sort(key=lambda x: x["hamming_distance"])
        return matches
    finally:
        release_connection(conn)


def find_exact_image(file_hash: str, exclude_claim_id: Optional[str] = None) -> Optional[Dict]:
    """
    Find exact image match by file hash.
    
    Excludes template-like images (banners, headers) based on aspect ratio.
    """
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        _float = "DOUBLE PRECISION" if USE_POSTGRES else "REAL"

        # Filter out images with extreme aspect ratios (banners/headers)
        # Aspect ratio > 5:1 or < 1:5 are likely templates
        if exclude_claim_id:
            cursor.execute(_sql(f"""
                SELECT id, claim_id, image_index, phash, exif_timestamp, width, height
                FROM warranty_claim_images 
                WHERE file_hash = ? AND claim_id != ?
                  AND width > 0 AND height > 0
                  AND (CAST(width AS {_float}) / height) <= 5.0
                  AND (CAST(height AS {_float}) / width) <= 5.0
                  AND height >= 200 AND width >= 200
            """), (file_hash, exclude_claim_id))
        else:
            cursor.execute(_sql(f"""
                SELECT id, claim_id, image_index, phash, exif_timestamp, width, height
                FROM warranty_claim_images 
                WHERE file_hash = ?
                  AND width > 0 AND height > 0
                  AND (CAST(width AS {_float}) / height) <= 5.0
                  AND (CAST(height AS {_float}) / width) <= 5.0
                  AND height >= 200 AND width >= 200
            """), (file_hash,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        release_connection(conn)


def get_hash_claim_count(file_hash: str) -> int:
    """
    Count how many DISTINCT claims contain this image hash.
    Used to detect template images that appear across many claims.
    """
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute(_sql("""
            SELECT COUNT(DISTINCT claim_id) 
            FROM warranty_claim_images 
            WHERE file_hash = ?
        """), (file_hash,))
        result = cursor.fetchone()
        if USE_POSTGRES:
            return result["count"] if result else 0
        return result[0] if result else 0
    finally:
        release_connection(conn)


def get_phash_claim_count(phash: str, max_hamming_distance: int = 5) -> int:
    """
    Count how many DISTINCT claims contain images with similar phash.
    Used to detect template images with slight variations.
    """
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute("SELECT DISTINCT claim_id, phash FROM warranty_claim_images")

        seen_claims = set()
        for row in cursor.fetchall():
            stored_phash = row["phash"]
            distance = _hamming_distance(phash, stored_phash)
            if distance <= max_hamming_distance:
                seen_claims.add(row["claim_id"])

        return len(seen_claims)
    finally:
        release_connection(conn)


def save_duplicate_match(
    claim_id_1: str,
    claim_id_2: str,
    match_type: str,
    similarity_score: float,
    image_index_1: Optional[int] = None,
    image_index_2: Optional[int] = None,
    details: Optional[str] = None
) -> int:
    """Record a detected duplicate match."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        params = (claim_id_1, claim_id_2, match_type, similarity_score,
                  image_index_1, image_index_2, details)

        base_sql = """INSERT INTO warranty_duplicate_matches 
            (claim_id_1, claim_id_2, match_type, similarity_score,
             image_index_1, image_index_2, details)"""

        if USE_POSTGRES:
            cursor.execute(f"""{base_sql}
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, params)
            row_id = cursor.fetchone()["id"]
        else:
            cursor.execute(f"""{base_sql}
                VALUES (?,?,?,?,?,?,?)
            """, params)
            row_id = cursor.lastrowid

        conn.commit()
        return row_id
    finally:
        release_connection(conn)


def get_duplicates_for_claim(claim_id: str) -> List[Dict]:
    """Get all duplicate matches for a claim."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute(_sql("""
            SELECT * FROM warranty_duplicate_matches 
            WHERE claim_id_1 = ? OR claim_id_2 = ?
            ORDER BY similarity_score DESC
        """), (claim_id, claim_id))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_connection(conn)


def get_benchmark(brand: Optional[str], issue_type: str) -> Optional[Dict]:
    """Get benchmark data for a brand and issue type."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)

        # Try brand-specific first
        if brand:
            cursor.execute(_sql("""
                SELECT * FROM warranty_benchmarks 
                WHERE brand = ? AND issue_type = ?
            """), (brand, issue_type))
            row = cursor.fetchone()
            if row:
                return dict(row)

        # Fall back to generic
        cursor.execute(_sql("""
            SELECT * FROM warranty_benchmarks 
            WHERE brand IS NULL AND issue_type = ?
        """), (issue_type,))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None
    finally:
        release_connection(conn)


def save_feedback(
    claim_id: str,
    verdict: str,
    adjuster_id: Optional[str] = None,
    notes: Optional[str] = None
) -> int:
    """Save adjuster feedback on a claim."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        params = (claim_id, adjuster_id, verdict, notes)

        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO warranty_feedback (claim_id, adjuster_id, verdict, notes)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, params)
            row_id = cursor.fetchone()["id"]
        else:
            cursor.execute("""
                INSERT INTO warranty_feedback (claim_id, adjuster_id, verdict, notes)
                VALUES (?, ?, ?, ?)
            """, params)
            row_id = cursor.lastrowid

        conn.commit()
        return row_id
    finally:
        release_connection(conn)


def update_dealer_statistics(dealer_id: str, dealer_name: Optional[str] = None):
    """Update aggregated statistics for a dealer."""
    if not dealer_id:
        return
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)

        # Calculate stats from claims
        cursor.execute(_sql("""
            SELECT 
                COUNT(*) as total_claims,
                COALESCE(SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END), 0) as approved_claims,
                COALESCE(SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END), 0) as rejected_claims,
                COALESCE(SUM(CASE WHEN is_suspicious = 1 THEN 1 ELSE 0 END), 0) as suspicious_count,
                AVG(total_amount) as avg_claim_amount,
                AVG(parts_cost) as avg_parts_cost,
                AVG(labor_cost) as avg_labor_cost,
                MIN(claim_date) as first_claim_date,
                MAX(claim_date) as last_claim_date
            FROM warranty_claims 
            WHERE dealer_id = ?
        """), (dealer_id,))
        stats = cursor.fetchone()

        if not stats or (stats["total_claims"] if isinstance(stats, dict) else stats[0]) == 0:
            return

        # Count duplicates
        cursor.execute(_sql("""
            SELECT COUNT(*) as cnt FROM warranty_duplicate_matches dm
            JOIN warranty_claims c ON (dm.claim_id_1 = c.id OR dm.claim_id_2 = c.id)
            WHERE c.dealer_id = ?
        """), (dealer_id,))
        dup_row = cursor.fetchone()
        dup_count = dup_row["cnt"] if USE_POSTGRES else dup_row[0]

        # Count confirmed fraud from feedback
        cursor.execute(_sql("""
            SELECT COUNT(*) as cnt FROM warranty_feedback f
            JOIN warranty_claims c ON f.claim_id = c.id
            WHERE c.dealer_id = ? AND f.verdict = 'CONFIRMED_FRAUD'
        """), (dealer_id,))
        fraud_row = cursor.fetchone()
        fraud_count = fraud_row["cnt"] if USE_POSTGRES else fraud_row[0]

        now = datetime.now().isoformat()

        params = (
            dealer_id, dealer_name,
            stats["total_claims"], stats["approved_claims"], stats["rejected_claims"],
            fraud_count, stats["avg_claim_amount"], stats["avg_parts_cost"],
            stats["avg_labor_cost"], dup_count, stats["suspicious_count"],
            stats["first_claim_date"], stats["last_claim_date"], now
        )

        _cols = """(dealer_id, dealer_name, total_claims, approved_claims, rejected_claims,
         fraud_confirmed, avg_claim_amount, avg_parts_cost, avg_labor_cost,
         duplicate_count, suspicious_count, first_claim_date, last_claim_date, last_updated)"""

        if USE_POSTGRES:
            cursor.execute(f"""
                INSERT INTO dealer_statistics {_cols}
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (dealer_id) DO UPDATE SET
                    dealer_name=EXCLUDED.dealer_name, total_claims=EXCLUDED.total_claims,
                    approved_claims=EXCLUDED.approved_claims, rejected_claims=EXCLUDED.rejected_claims,
                    fraud_confirmed=EXCLUDED.fraud_confirmed, avg_claim_amount=EXCLUDED.avg_claim_amount,
                    avg_parts_cost=EXCLUDED.avg_parts_cost, avg_labor_cost=EXCLUDED.avg_labor_cost,
                    duplicate_count=EXCLUDED.duplicate_count, suspicious_count=EXCLUDED.suspicious_count,
                    first_claim_date=EXCLUDED.first_claim_date, last_claim_date=EXCLUDED.last_claim_date,
                    last_updated=EXCLUDED.last_updated
            """, params)
        else:
            cursor.execute(f"""
                INSERT OR REPLACE INTO dealer_statistics {_cols}
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, params)

        conn.commit()
    finally:
        release_connection(conn)


def get_dealer_statistics(dealer_id: str) -> Optional[Dict]:
    """Get statistics for a dealer."""
    conn = get_connection()
    try:
        cursor = _get_cursor(conn)
        cursor.execute(_sql("SELECT * FROM dealer_statistics WHERE dealer_id = ?"), (dealer_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        release_connection(conn)


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a database row to a dictionary with parsed JSON fields."""
    d = dict(row)
    
    # Parse JSON fields
    for field in ["fraud_signals", "warnings"]:
        if field in d and d[field]:
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                d[field] = []
    
    return d


def _hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate Hamming distance between two hex hash strings."""
    if len(hash1) != len(hash2):
        return 64  # Max distance for 64-bit hash
    
    # Convert hex to binary and count differing bits
    try:
        int1 = int(hash1, 16)
        int2 = int(hash2, 16)
        xor = int1 ^ int2
        return bin(xor).count('1')
    except ValueError:
        return 64
