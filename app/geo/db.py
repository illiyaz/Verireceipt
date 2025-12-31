"""
Geo database module - SQLite loader and queries for postal patterns, cities, and terms.
"""

import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading

# Thread-local storage for DB connections
_thread_local = threading.local()

def get_db_path() -> Path:
    """Get path to geo.sqlite database."""
    return Path(__file__).parent.parent / "data" / "geo.sqlite"

def get_connection() -> sqlite3.Connection:
    """Get thread-local database connection."""
    if not hasattr(_thread_local, "conn"):
        db_path = get_db_path()
        if not db_path.exists():
            # Bootstrap database if it doesn't exist
            from .bootstrap import bootstrap_geo_db
            bootstrap_geo_db()
        
        _thread_local.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _thread_local.conn.row_factory = sqlite3.Row
    
    return _thread_local.conn

def query_postal_patterns() -> List[Dict[str, Any]]:
    """Get all postal patterns."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT country_code, pattern, weight, description
        FROM postal_patterns
        ORDER BY weight DESC
    """)
    return [dict(row) for row in cursor.fetchall()]

def query_cities(country_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get cities, optionally filtered by country."""
    conn = get_connection()
    if country_code:
        cursor = conn.execute("""
            SELECT country_code, name_norm, display_name, admin1, alt_names, pop_rank
            FROM cities
            WHERE country_code = ?
            ORDER BY pop_rank DESC
        """, (country_code,))
    else:
        cursor = conn.execute("""
            SELECT country_code, name_norm, display_name, admin1, alt_names, pop_rank
            FROM cities
            ORDER BY pop_rank DESC
        """)
    return [dict(row) for row in cursor.fetchall()]

def query_terms(country_code: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get terms, optionally filtered by country and/or kind."""
    conn = get_connection()
    
    conditions = []
    params = []
    
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)
    
    if kind:
        conditions.append("kind = ?")
        params.append(kind)
    
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    cursor = conn.execute(f"""
        SELECT country_code, kind, token_norm, weight, examples
        FROM terms
        {where_clause}
        ORDER BY weight DESC
    """, params)
    
    return [dict(row) for row in cursor.fetchall()]

def search_city(city_name: str) -> List[Dict[str, Any]]:
    """Search for cities by name (normalized or alt names)."""
    conn = get_connection()
    city_norm = city_name.lower().strip()
    
    cursor = conn.execute("""
        SELECT country_code, name_norm, display_name, admin1, alt_names, pop_rank
        FROM cities
        WHERE name_norm = ? OR alt_names LIKE ?
        ORDER BY pop_rank DESC
        LIMIT 10
    """, (city_norm, f"%{city_norm}%"))
    
    return [dict(row) for row in cursor.fetchall()]

def close_connection():
    """Close thread-local database connection."""
    if hasattr(_thread_local, "conn"):
        _thread_local.conn.close()
        delattr(_thread_local, "conn")
