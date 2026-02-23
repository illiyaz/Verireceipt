"""Database operations for authentication and authorization.

Dual-mode: PostgreSQL (production/Render) or SQLite (local dev).
Reuses the connection infrastructure from warranty.db.
"""

import os
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")


def _get_connection():
    """Get DB connection from warranty pool."""
    from ..warranty.db import get_connection
    return get_connection()


def _release(conn):
    from ..warranty.db import release_connection
    release_connection(conn)


def _cursor(conn):
    from ..warranty.db import _get_cursor
    return _get_cursor(conn)


def _sql(query: str) -> str:
    from ..warranty.db import _sql as wsql
    return wsql(query)


# ---------- Bootstrap ----------

def bootstrap_auth_tables(conn):
    """Create auth tables. Safe to call multiple times (IF NOT EXISTS)."""
    cursor = conn.cursor()

    if USE_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                permissions TEXT DEFAULT '[]',
                is_system BOOLEAN DEFAULT FALSE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                phone TEXT,
                role_id TEXT REFERENCES roles(id),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                last_login TEXT,
                reset_token TEXT,
                reset_token_expiry TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                username TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                permissions TEXT DEFAULT '[]',
                is_system INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                phone TEXT,
                role_id TEXT REFERENCES roles(id),
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                last_login TEXT,
                reset_token TEXT,
                reset_token_expiry TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                username TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")

    conn.commit()


def seed_default_roles(conn):
    """Insert default roles if they don't exist."""
    from .models import DEFAULT_ROLES
    cursor = _cursor(conn)

    for role_name, role_def in DEFAULT_ROLES.items():
        role_id = f"role_{role_name}"
        perms_json = json.dumps(role_def["permissions"])
        is_sys = 1 if role_def.get("is_system") else 0

        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO roles (id, name, description, permissions, is_system, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (role_id, role_name, role_def["description"], perms_json, bool(is_sys), datetime.now().isoformat()))
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO roles (id, name, description, permissions, is_system, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (role_id, role_name, role_def["description"], perms_json, is_sys, datetime.now().isoformat()))

    conn.commit()


def seed_default_admin(conn):
    """Create default admin user if no users exist."""
    cursor = _cursor(conn)
    cursor.execute(_sql("SELECT COUNT(*) as cnt FROM users"))
    row = cursor.fetchone()
    count = dict(row).get("cnt", 0) if row else 0

    if count == 0:
        admin_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        pw_hash = pwd_context.hash("admin123")

        is_active_val = True if USE_POSTGRES else 1
        cursor.execute(_sql("""
            INSERT INTO users (id, username, email, password_hash, full_name, role_id, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (admin_id, "admin", "admin@verireceipt.com", pw_hash, "System Administrator", "role_admin", is_active_val, now, now))
        conn.commit()
        print("✅ Default admin user created (username: admin, password: admin123)")


# ---------- User CRUD ----------

def _row_to_dict(row) -> Dict[str, Any]:
    """Convert any row type to dict."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return {}


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("SELECT * FROM users WHERE username = ?"), (username,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        _release(conn)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("SELECT * FROM users WHERE email = ?"), (email,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        _release(conn)


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("SELECT * FROM users WHERE id = ?"), (user_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        _release(conn)


def create_user(username: str, email: str, password: str, full_name: str = None,
                phone: str = None, role_id: str = "role_analyst") -> Dict[str, Any]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        user_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        pw_hash = pwd_context.hash(password)

        is_active_val = True if USE_POSTGRES else 1
        cursor.execute(_sql("""
            INSERT INTO users (id, username, email, password_hash, full_name, phone, role_id, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (user_id, username, email, pw_hash, full_name, phone, role_id, is_active_val, now, now))
        conn.commit()

        return {"id": user_id, "username": username, "email": email, "role_id": role_id}
    finally:
        _release(conn)


def update_user(user_id: str, updates: Dict[str, Any]) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        sets = []
        params = []
        for key in ["email", "full_name", "phone", "role_id", "is_active"]:
            if key in updates and updates[key] is not None:
                sets.append(f"{key} = ?")
                val = updates[key]
                if key == "is_active":
                    val = bool(val) if USE_POSTGRES else (1 if val else 0)
                params.append(val)
        if not sets:
            return False
        sets.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(user_id)

        cursor.execute(_sql(f"UPDATE users SET {', '.join(sets)} WHERE id = ?"), tuple(params))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        _release(conn)


def update_password(user_id: str, new_password: str) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        pw_hash = pwd_context.hash(new_password)
        now = datetime.now().isoformat()
        cursor.execute(_sql("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?"),
                        (pw_hash, now, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        _release(conn)


def set_reset_token(user_id: str, token: str, expiry: str) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE id = ?"),
                        (token, expiry, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        _release(conn)


def get_user_by_reset_token(token: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("SELECT * FROM users WHERE reset_token = ?"), (token,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        _release(conn)


def clear_reset_token(user_id: str) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("UPDATE users SET reset_token = NULL, reset_token_expiry = NULL WHERE id = ?"),
                        (user_id,))
        conn.commit()
        return True
    finally:
        _release(conn)


def update_last_login(user_id: str):
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("UPDATE users SET last_login = ? WHERE id = ?"),
                        (datetime.now().isoformat(), user_id))
        conn.commit()
    finally:
        _release(conn)


def list_users(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("""
            SELECT u.*, r.name as role_name, r.permissions as role_permissions
            FROM users u LEFT JOIN roles r ON u.role_id = r.id
            ORDER BY u.created_at DESC
            LIMIT ? OFFSET ?
        """), (limit, offset))
        return [_row_to_dict(r) for r in cursor.fetchall()]
    finally:
        _release(conn)


def delete_user(user_id: str) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("DELETE FROM users WHERE id = ?"), (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        _release(conn)


def count_users() -> int:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute("SELECT COUNT(*) as cnt FROM users")
        row = cursor.fetchone()
        return _row_to_dict(row).get("cnt", 0)
    finally:
        _release(conn)


# ---------- Role CRUD ----------

def get_role(role_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("SELECT * FROM roles WHERE id = ?"), (role_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        _release(conn)


def get_role_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute(_sql("SELECT * FROM roles WHERE name = ?"), (name,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        _release(conn)


def list_roles() -> List[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        cursor.execute("SELECT * FROM roles ORDER BY name")
        return [_row_to_dict(r) for r in cursor.fetchall()]
    finally:
        _release(conn)


def create_role(name: str, description: str = None, permissions: List[str] = None) -> Dict[str, Any]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        role_id = f"role_{name.lower().replace(' ', '_')}"
        now = datetime.now().isoformat()
        perms_json = json.dumps(permissions or [])

        is_sys_val = False if USE_POSTGRES else 0
        cursor.execute(_sql("""
            INSERT INTO roles (id, name, description, permissions, is_system, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """), (role_id, name, description, perms_json, is_sys_val, now))
        conn.commit()
        return {"id": role_id, "name": name, "description": description, "permissions": permissions or []}
    finally:
        _release(conn)


def update_role(role_id: str, description: str = None, permissions: List[str] = None) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        sets = []
        params = []
        if description is not None:
            sets.append("description = ?")
            params.append(description)
        if permissions is not None:
            sets.append("permissions = ?")
            params.append(json.dumps(permissions))
        if not sets:
            return False
        params.append(role_id)
        cursor.execute(_sql(f"UPDATE roles SET {', '.join(sets)} WHERE id = ?"), tuple(params))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        _release(conn)


def delete_role(role_id: str) -> bool:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        # Don't delete system roles
        cursor.execute(_sql("SELECT is_system FROM roles WHERE id = ?"), (role_id,))
        row = cursor.fetchone()
        if row and _row_to_dict(row).get("is_system"):
            return False
        cursor.execute(_sql("DELETE FROM roles WHERE id = ?"), (role_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        _release(conn)


# ---------- Audit Log ----------

def log_audit(user_id: str, username: str, action: str,
              resource_type: str = None, resource_id: str = None,
              details: str = None, ip_address: str = None, user_agent: str = None):
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        log_id = str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()
        cursor.execute(_sql("""
            INSERT INTO audit_log (id, user_id, username, action, resource_type, resource_id, details, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (log_id, user_id, username, action, resource_type, resource_id, details, ip_address, user_agent, now))
        conn.commit()
    except Exception as e:
        print(f"Audit log error: {e}")
    finally:
        _release(conn)


def get_audit_logs(limit: int = 100, offset: int = 0,
                   user_id: str = None, action: str = None) -> List[Dict[str, Any]]:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        conditions = []
        params = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if action:
            conditions.append("action = ?")
            params.append(action)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        cursor.execute(_sql(f"""
            SELECT * FROM audit_log {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """), tuple(params))
        return [_row_to_dict(r) for r in cursor.fetchall()]
    finally:
        _release(conn)


def count_audit_logs(user_id: str = None, action: str = None) -> int:
    conn = _get_connection()
    try:
        cursor = _cursor(conn)
        conditions = []
        params = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if action:
            conditions.append("action = ?")
            params.append(action)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor.execute(_sql(f"SELECT COUNT(*) as cnt FROM audit_log {where}"), tuple(params))
        row = cursor.fetchone()
        return _row_to_dict(row).get("cnt", 0)
    finally:
        _release(conn)


# ---------- Init ----------

def init_auth_db():
    """Initialize auth tables and seed data. Call on app startup."""
    conn = _get_connection()
    try:
        bootstrap_auth_tables(conn)
        seed_default_roles(conn)
        seed_default_admin(conn)
    finally:
        _release(conn)
