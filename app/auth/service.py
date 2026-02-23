"""JWT token service and authentication logic."""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from jose import jwt, JWTError
from passlib.context import CryptContext

from .models import Permissions

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "verireceipt-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8 hours default


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def create_reset_token(user_id: str) -> str:
    """Create a password reset token valid for 1 hour."""
    expire = datetime.utcnow() + timedelta(hours=1)
    return jwt.encode({"sub": user_id, "type": "reset", "exp": expire},
                      JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_reset_token(token: str) -> Optional[str]:
    """Verify reset token and return user_id."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def get_user_permissions(role_permissions_json: str) -> List[str]:
    """Parse permissions from role JSON string."""
    try:
        perms = json.loads(role_permissions_json) if isinstance(role_permissions_json, str) else role_permissions_json
        return perms if isinstance(perms, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def has_permission(user_permissions: List[str], required: str) -> bool:
    """Check if user has the required permission."""
    if Permissions.ADMIN_FULL in user_permissions:
        return True
    return required in user_permissions


def has_any_permission(user_permissions: List[str], required: List[str]) -> bool:
    """Check if user has any of the required permissions."""
    if Permissions.ADMIN_FULL in user_permissions:
        return True
    return any(p in user_permissions for p in required)
