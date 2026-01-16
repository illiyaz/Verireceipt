"""
Geo database module - SQLite loader and queries for postal patterns, cities, and terms.
"""

import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
import json

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

# ---------------------------------------------------------------------------
# Geo / VAT knowledge queries
# ---------------------------------------------------------------------------

def _active_clause() -> str:
    return "(effective_to IS NULL OR date(effective_to) >= date('now'))"


def query_geo_profile(country_code: str) -> Optional[Dict[str, Any]]:
    """
    Fetch active geo profile for a country.
    """
    conn = get_connection()
    cursor = conn.execute(
        f"""
        SELECT *
        FROM geo_profiles
        WHERE country_code = ?
          AND {_active_clause()}
        ORDER BY effective_from DESC
        LIMIT 1
        """,
        (country_code,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def query_vat_rules(country_code: str) -> List[Dict[str, Any]]:
    """
    Fetch active VAT/GST rules for a country.
    """
    conn = get_connection()
    cursor = conn.execute(
        f"""
        SELECT *
        FROM vat_rules
        WHERE country_code = ?
          AND {_active_clause()}
        ORDER BY rate DESC
        """,
        (country_code,),
    )
    return [dict(r) for r in cursor.fetchall()]


def query_currency_countries(currency: str) -> List[Dict[str, Any]]:
    """
    Fetch countries commonly associated with a currency.
    """
    conn = get_connection()
    cursor = conn.execute(
        f"""
        SELECT *
        FROM currency_country_map
        WHERE currency = ?
          AND {_active_clause()}
        ORDER BY is_primary DESC, weight DESC
        """,
        (currency,),
    )
    return [dict(r) for r in cursor.fetchall()]


def query_doc_expectations(
    *,
    country_code: str,
    region: Optional[str],
    doc_family: str,
    doc_subtype: str,
) -> Optional[Dict[str, Any]]:
    """
    Resolve document expectations with fallback:
    COUNTRY → REGION → GLOBAL.
    """
    conn = get_connection()

    def _fetch(scope: str, code: str) -> Optional[Dict[str, Any]]:
        cur = conn.execute(
            f"""
            SELECT *
            FROM doc_expectations_by_geo
            WHERE geo_scope = ?
              AND geo_code = ?
              AND doc_family = ?
              AND doc_subtype = ?
              AND {_active_clause()}
            ORDER BY effective_from DESC
            LIMIT 1
            """,
            (scope, code, doc_family, doc_subtype),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    row = _fetch("COUNTRY", country_code)
    if row:
        return row

    if region:
        row = _fetch("REGION", region)
        if row:
            return row

    return _fetch("GLOBAL", "*")

# NOTE:
# Tables expected by this module:
# - geo_profiles
# - vat_rules
# - currency_country_map
# - doc_expectations_by_geo
#
# These are bootstrapped by app.geo.bootstrap.bootstrap_geo_db
