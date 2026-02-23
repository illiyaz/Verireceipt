"""FastAPI dependencies for authentication and authorization."""

from typing import Optional, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .service import decode_token, get_user_permissions, has_permission
from . import db as auth_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Extract and validate JWT token, return user dict with permissions."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = auth_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Fetch role permissions
    role = auth_db.get_role(user.get("role_id", ""))
    permissions = get_user_permissions(role.get("permissions", "[]")) if role else []

    user["permissions"] = permissions
    user["role_name"] = role.get("name", "") if role else ""

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Like get_current_user but returns None instead of 401 if no token."""
    if credentials is None:
        return None

    payload = decode_token(credentials.credentials)
    if payload is None:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = auth_db.get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        return None

    role = auth_db.get_role(user.get("role_id", ""))
    permissions = get_user_permissions(role.get("permissions", "[]")) if role else []
    user["permissions"] = permissions
    user["role_name"] = role.get("name", "") if role else ""

    return user


def require_permission(permission: str):
    """Dependency factory: require a specific permission."""
    async def _check(current_user: dict = Depends(get_current_user)):
        if not has_permission(current_user.get("permissions", []), permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required",
            )
        return current_user
    return _check


def require_any_permission(permissions: List[str]):
    """Dependency factory: require any of the given permissions."""
    async def _check(current_user: dict = Depends(get_current_user)):
        user_perms = current_user.get("permissions", [])
        from .models import Permissions
        if Permissions.ADMIN_FULL in user_perms:
            return current_user
        if not any(p in user_perms for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: one of {permissions} required",
            )
        return current_user
    return _check


def require_admin():
    """Dependency: require admin role."""
    return require_permission("admin:full")
