"""Pydantic models for authentication and authorization."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---------- Request models ----------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    phone: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: Optional[str] = None
    is_active: Optional[bool] = None


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


# ---------- Response models ----------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: str
    role_name: Optional[str] = None
    permissions: List[str] = []
    is_active: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class RoleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    permissions: List[str] = []
    is_system: bool = False
    created_at: Optional[str] = None


class AuditLogEntry(BaseModel):
    id: Optional[str] = None
    user_id: str
    username: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[str] = None


# ---------- Permission constants ----------

class Permissions:
    # Claims
    CLAIMS_VIEW = "claims:view"
    CLAIMS_UPLOAD = "claims:upload"
    CLAIMS_ANALYZE = "claims:analyze"
    CLAIMS_DELETE = "claims:delete"

    # Dashboard
    DASHBOARD_VIEW = "dashboard:view"

    # Users
    USERS_VIEW = "users:view"
    USERS_CREATE = "users:create"
    USERS_EDIT = "users:edit"
    USERS_DELETE = "users:delete"

    # Roles
    ROLES_VIEW = "roles:view"
    ROLES_CREATE = "roles:create"
    ROLES_EDIT = "roles:edit"
    ROLES_DELETE = "roles:delete"

    # Admin
    ADMIN_FULL = "admin:full"

    # Audit
    AUDIT_VIEW = "audit:view"


# Default role definitions
DEFAULT_ROLES = {
    "admin": {
        "description": "Full system administrator",
        "permissions": [Permissions.ADMIN_FULL],
        "is_system": True,
    },
    "analyst": {
        "description": "Can upload, view, and analyze warranty claims",
        "permissions": [
            Permissions.CLAIMS_VIEW,
            Permissions.CLAIMS_UPLOAD,
            Permissions.CLAIMS_ANALYZE,
            Permissions.DASHBOARD_VIEW,
        ],
        "is_system": True,
    },
    "viewer": {
        "description": "Read-only access to claims and dashboard",
        "permissions": [
            Permissions.CLAIMS_VIEW,
            Permissions.DASHBOARD_VIEW,
        ],
        "is_system": True,
    },
}
