"""Authentication and admin API routes."""

import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request

from .models import (
    LoginRequest, RegisterRequest, ChangePasswordRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
    UpdateUserRequest, CreateRoleRequest, UpdateRoleRequest,
    TokenResponse, UserResponse, RoleResponse, AuditLogEntry,
    Permissions,
)
from .service import (
    verify_password, create_access_token, create_reset_token,
    verify_reset_token, get_user_permissions, JWT_EXPIRE_MINUTES,
)
from .dependencies import get_current_user, require_permission, require_any_permission
from . import db as auth_db

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _user_response(user: dict) -> dict:
    perms = get_user_permissions(user.get("role_permissions", user.get("permissions", "[]")))
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "full_name": user.get("full_name"),
        "phone": user.get("phone"),
        "role_id": user.get("role_id", ""),
        "role_name": user.get("role_name", ""),
        "permissions": perms if isinstance(perms, list) else [],
        "is_active": bool(user.get("is_active")),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
    }


# ==================== Auth Routes ====================

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """Authenticate user and return JWT token."""
    user = auth_db.get_user_by_username(body.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Update last login
    auth_db.update_last_login(user["id"])

    # Get role info
    role = auth_db.get_role(user.get("role_id", ""))
    perms = get_user_permissions(role.get("permissions", "[]")) if role else []

    # Create token
    token = create_access_token({"sub": user["id"], "username": user["username"], "role": user.get("role_id", "")})

    # Audit
    auth_db.log_audit(user["id"], user["username"], "login", ip_address=_client_ip(request),
                      user_agent=request.headers.get("user-agent", ""))

    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user={
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "role_id": user.get("role_id", ""),
            "role_name": role.get("name", "") if role else "",
            "permissions": perms,
        },
    )


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    """Register a new user (default role: analyst)."""
    if auth_db.get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if auth_db.get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = auth_db.create_user(
        username=body.username,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        phone=body.phone,
        role_id="role_analyst",
    )

    auth_db.log_audit(user["id"], body.username, "register", ip_address=_client_ip(request))

    return {"message": "Registration successful", "user_id": user["id"]}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return _user_response(current_user)


@router.put("/me/password")
async def change_password(body: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    """Change current user's password."""
    user = auth_db.get_user_by_id(current_user["id"])
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    auth_db.update_password(current_user["id"], body.new_password)
    auth_db.log_audit(current_user["id"], current_user["username"], "password_change")
    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    """Request a password reset token. In production, this sends an email."""
    user = auth_db.get_user_by_email(body.email)
    if not user:
        # Don't reveal if email exists
        return {"message": "If the email is registered, a reset link has been sent."}

    token = create_reset_token(user["id"])
    expiry = (datetime.utcnow().isoformat())
    auth_db.set_reset_token(user["id"], token, expiry)

    # In production: send email via SMTP
    # For now, return token in response (dev mode)
    import os
    if os.getenv("SMTP_HOST"):
        # TODO: Send email via SMTP
        return {"message": "If the email is registered, a reset link has been sent."}
    else:
        # Dev mode: return token directly
        return {
            "message": "Reset token generated (dev mode — configure SMTP_HOST for email delivery)",
            "reset_token": token,
            "note": "In production, this token is sent via email, not in the API response.",
        }


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    """Reset password using a valid reset token."""
    user_id = verify_reset_token(body.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = auth_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    auth_db.update_password(user_id, body.new_password)
    auth_db.clear_reset_token(user_id)
    auth_db.log_audit(user_id, user.get("username", ""), "password_reset")
    return {"message": "Password reset successful"}


# ==================== Admin: User Management ====================

@admin_router.get("/users")
async def list_users(
    limit: int = 100, offset: int = 0,
    current_user: dict = Depends(require_permission(Permissions.USERS_VIEW)),
):
    """List all users (admin only)."""
    users = auth_db.list_users(limit, offset)
    total = auth_db.count_users()
    result = []
    for u in users:
        perms = get_user_permissions(u.get("role_permissions", "[]"))
        result.append({
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "full_name": u.get("full_name"),
            "phone": u.get("phone"),
            "role_id": u.get("role_id", ""),
            "role_name": u.get("role_name", ""),
            "permissions": perms,
            "is_active": bool(u.get("is_active")),
            "created_at": u.get("created_at"),
            "last_login": u.get("last_login"),
        })
    return {"users": result, "total": total}


@admin_router.post("/users")
async def admin_create_user(
    body: RegisterRequest,
    role_id: Optional[str] = "role_analyst",
    request: Request = None,
    current_user: dict = Depends(require_permission(Permissions.USERS_CREATE)),
):
    """Create a new user (admin only)."""
    if auth_db.get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if auth_db.get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = auth_db.create_user(
        username=body.username,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        phone=body.phone,
        role_id=role_id,
    )

    auth_db.log_audit(current_user["id"], current_user["username"], "user_create",
                      resource_type="user", resource_id=user["id"],
                      details=f"Created user {body.username} with role {role_id}",
                      ip_address=_client_ip(request) if request else None)
    return {"message": "User created", "user": user}


@admin_router.put("/users/{user_id}")
async def admin_update_user(
    user_id: str,
    body: UpdateUserRequest,
    request: Request,
    current_user: dict = Depends(require_permission(Permissions.USERS_EDIT)),
):
    """Update a user (admin only)."""
    target = auth_db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    updates = body.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    auth_db.update_user(user_id, updates)
    auth_db.log_audit(current_user["id"], current_user["username"], "user_update",
                      resource_type="user", resource_id=user_id,
                      details=json.dumps(updates),
                      ip_address=_client_ip(request))
    return {"message": "User updated"}


@admin_router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_permission(Permissions.USERS_DELETE)),
):
    """Delete a user (admin only)."""
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    target = auth_db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    auth_db.delete_user(user_id)
    auth_db.log_audit(current_user["id"], current_user["username"], "user_delete",
                      resource_type="user", resource_id=user_id,
                      details=f"Deleted user {target.get('username', '')}",
                      ip_address=_client_ip(request))
    return {"message": "User deleted"}


# ==================== Admin: Role Management ====================

@admin_router.get("/roles")
async def list_roles(current_user: dict = Depends(require_permission(Permissions.ROLES_VIEW))):
    """List all roles (admin only)."""
    roles = auth_db.list_roles()
    return {"roles": [{
        "id": r["id"],
        "name": r["name"],
        "description": r.get("description"),
        "permissions": json.loads(r.get("permissions", "[]")) if isinstance(r.get("permissions"), str) else r.get("permissions", []),
        "is_system": bool(r.get("is_system")),
        "created_at": r.get("created_at"),
    } for r in roles]}


@admin_router.post("/roles")
async def admin_create_role(
    body: CreateRoleRequest,
    request: Request,
    current_user: dict = Depends(require_permission(Permissions.ROLES_CREATE)),
):
    """Create a new role (admin only)."""
    if auth_db.get_role_by_name(body.name):
        raise HTTPException(status_code=400, detail="Role name already exists")

    role = auth_db.create_role(body.name, body.description, body.permissions)
    auth_db.log_audit(current_user["id"], current_user["username"], "role_create",
                      resource_type="role", resource_id=role["id"],
                      details=f"Created role {body.name}",
                      ip_address=_client_ip(request))
    return {"message": "Role created", "role": role}


@admin_router.put("/roles/{role_id}")
async def admin_update_role(
    role_id: str,
    body: UpdateRoleRequest,
    request: Request,
    current_user: dict = Depends(require_permission(Permissions.ROLES_EDIT)),
):
    """Update a role (admin only). Cannot modify system roles' names."""
    role = auth_db.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    auth_db.update_role(role_id, body.description, body.permissions)
    auth_db.log_audit(current_user["id"], current_user["username"], "role_update",
                      resource_type="role", resource_id=role_id,
                      ip_address=_client_ip(request))
    return {"message": "Role updated"}


@admin_router.delete("/roles/{role_id}")
async def admin_delete_role(
    role_id: str,
    request: Request,
    current_user: dict = Depends(require_permission(Permissions.ROLES_DELETE)),
):
    """Delete a custom role (admin only). System roles cannot be deleted."""
    role = auth_db.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    if not auth_db.delete_role(role_id):
        raise HTTPException(status_code=400, detail="Failed to delete role")

    auth_db.log_audit(current_user["id"], current_user["username"], "role_delete",
                      resource_type="role", resource_id=role_id,
                      details=f"Deleted role {role.get('name', '')}",
                      ip_address=_client_ip(request))
    return {"message": "Role deleted"}


# ==================== Admin: Audit Logs ====================

@admin_router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 100, offset: int = 0,
    user_id: Optional[str] = None, action: Optional[str] = None,
    current_user: dict = Depends(require_permission(Permissions.AUDIT_VIEW)),
):
    """List audit logs (admin only)."""
    logs = auth_db.get_audit_logs(limit, offset, user_id, action)
    total = auth_db.count_audit_logs(user_id, action)
    return {"logs": logs, "total": total}


# ==================== Available Permissions ====================

@admin_router.get("/permissions")
async def list_permissions(current_user: dict = Depends(get_current_user)):
    """List all available permissions."""
    return {"permissions": [
        {"key": v, "label": v.replace(":", " → ").replace("_", " ").title()}
        for k, v in vars(Permissions).items()
        if not k.startswith("_")
    ]}
