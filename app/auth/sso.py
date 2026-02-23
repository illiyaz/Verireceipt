"""SSO Integration Scaffolding — SAML 2.0 and OpenID Connect (OIDC).

This module provides the foundation for Single Sign-On integration.
It is NOT active by default. To enable:

1. Set SSO_ENABLED=true in environment
2. Configure provider-specific settings (see below)
3. Install required packages:
   - SAML: pip install python3-saml
   - OIDC: pip install authlib httpx

Environment Variables:
    SSO_ENABLED=true
    SSO_PROVIDER=saml|oidc

    # SAML 2.0
    SAML_IDP_ENTITY_ID=https://idp.example.com
    SAML_IDP_SSO_URL=https://idp.example.com/sso
    SAML_IDP_SLO_URL=https://idp.example.com/slo
    SAML_IDP_CERT=<base64 cert>
    SAML_SP_ENTITY_ID=https://verireceipt.example.com
    SAML_SP_ACS_URL=https://verireceipt.example.com/auth/sso/saml/callback

    # OIDC (Google, Azure AD, Okta, etc.)
    OIDC_CLIENT_ID=your-client-id
    OIDC_CLIENT_SECRET=your-client-secret
    OIDC_DISCOVERY_URL=https://accounts.google.com/.well-known/openid-configuration
    OIDC_REDIRECT_URI=https://verireceipt.example.com/auth/sso/oidc/callback
    OIDC_SCOPES=openid email profile

    # Shared
    SSO_DEFAULT_ROLE=role_analyst
    SSO_AUTO_CREATE_USER=true
"""

import os
import uuid
import json
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

SSO_ENABLED = os.getenv("SSO_ENABLED", "false").lower() == "true"
SSO_PROVIDER = os.getenv("SSO_PROVIDER", "oidc")  # saml or oidc
SSO_DEFAULT_ROLE = os.getenv("SSO_DEFAULT_ROLE", "role_analyst")
SSO_AUTO_CREATE = os.getenv("SSO_AUTO_CREATE_USER", "true").lower() == "true"

router = APIRouter(prefix="/auth/sso", tags=["sso"])


# ==================== OIDC (OpenID Connect) ====================

class OIDCProvider:
    """OpenID Connect provider for Google, Azure AD, Okta, etc."""

    def __init__(self):
        self.client_id = os.getenv("OIDC_CLIENT_ID", "")
        self.client_secret = os.getenv("OIDC_CLIENT_SECRET", "")
        self.discovery_url = os.getenv("OIDC_DISCOVERY_URL", "")
        self.redirect_uri = os.getenv("OIDC_REDIRECT_URI", "")
        self.scopes = os.getenv("OIDC_SCOPES", "openid email profile").split()
        self._metadata = None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.discovery_url)

    async def get_metadata(self) -> dict:
        """Fetch OIDC discovery metadata."""
        if self._metadata:
            return self._metadata
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.discovery_url)
                self._metadata = resp.json()
                return self._metadata
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OIDC discovery failed: {e}")

    async def get_authorization_url(self, state: str) -> str:
        """Build the authorization URL to redirect user to IdP."""
        metadata = await self.get_metadata()
        auth_endpoint = metadata.get("authorization_endpoint")
        if not auth_endpoint:
            raise HTTPException(status_code=500, detail="No authorization_endpoint in OIDC metadata")

        from urllib.parse import urlencode
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{auth_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens and user info."""
        metadata = await self.get_metadata()
        token_endpoint = metadata.get("token_endpoint")
        userinfo_endpoint = metadata.get("userinfo_endpoint")

        import httpx
        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_resp = await client.post(token_endpoint, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            })
            tokens = token_resp.json()

            if "error" in tokens:
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {tokens.get('error_description', tokens['error'])}")

            # Get user info
            access_token = tokens.get("access_token")
            userinfo_resp = await client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
            userinfo = userinfo_resp.json()

            return {
                "email": userinfo.get("email"),
                "name": userinfo.get("name"),
                "sub": userinfo.get("sub"),
                "tokens": tokens,
            }


# ==================== SAML 2.0 ====================

class SAMLProvider:
    """SAML 2.0 provider scaffolding."""

    def __init__(self):
        self.idp_entity_id = os.getenv("SAML_IDP_ENTITY_ID", "")
        self.idp_sso_url = os.getenv("SAML_IDP_SSO_URL", "")
        self.idp_slo_url = os.getenv("SAML_IDP_SLO_URL", "")
        self.idp_cert = os.getenv("SAML_IDP_CERT", "")
        self.sp_entity_id = os.getenv("SAML_SP_ENTITY_ID", "")
        self.sp_acs_url = os.getenv("SAML_SP_ACS_URL", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.idp_entity_id and self.idp_sso_url and self.sp_entity_id)

    def get_settings(self) -> dict:
        """Return python3-saml compatible settings dict."""
        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": self.sp_entity_id,
                "assertionConsumerService": {
                    "url": self.sp_acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
            },
            "idp": {
                "entityId": self.idp_entity_id,
                "singleSignOnService": {
                    "url": self.idp_sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "singleLogoutService": {
                    "url": self.idp_slo_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": self.idp_cert,
            },
        }


# ==================== Instances ====================

_oidc = OIDCProvider()
_saml = SAMLProvider()


# ==================== SSO Helper ====================

def _find_or_create_sso_user(email: str, full_name: str = None) -> dict:
    """Find existing user by email or auto-create if SSO_AUTO_CREATE is enabled."""
    from . import db as auth_db

    user = auth_db.get_user_by_email(email)
    if user:
        return user

    if not SSO_AUTO_CREATE:
        raise HTTPException(status_code=403, detail="No account found for this email. Contact your administrator.")

    # Auto-create user from SSO
    username = email.split("@")[0]
    # Ensure unique username
    base_username = username
    counter = 1
    while auth_db.get_user_by_username(username):
        username = f"{base_username}{counter}"
        counter += 1

    # Random password (SSO users don't use password login)
    import secrets
    password = secrets.token_urlsafe(32)

    user = auth_db.create_user(
        username=username,
        email=email,
        password=password,
        full_name=full_name,
        role_id=SSO_DEFAULT_ROLE,
    )
    auth_db.log_audit(user["id"], username, "sso_auto_create",
                      details=f"Auto-created from SSO ({SSO_PROVIDER})")
    return auth_db.get_user_by_id(user["id"])


# ==================== Routes ====================

@router.get("/status")
async def sso_status():
    """Check SSO configuration status."""
    return {
        "sso_enabled": SSO_ENABLED,
        "provider": SSO_PROVIDER if SSO_ENABLED else None,
        "oidc_configured": _oidc.is_configured,
        "saml_configured": _saml.is_configured,
    }


@router.get("/login")
async def sso_login(request: Request):
    """Initiate SSO login flow. Redirects to IdP."""
    if not SSO_ENABLED:
        raise HTTPException(status_code=400, detail="SSO is not enabled")

    state = str(uuid.uuid4())

    if SSO_PROVIDER == "oidc":
        if not _oidc.is_configured:
            raise HTTPException(status_code=500, detail="OIDC is not configured")
        url = await _oidc.get_authorization_url(state)
        return RedirectResponse(url)

    elif SSO_PROVIDER == "saml":
        if not _saml.is_configured:
            raise HTTPException(status_code=500, detail="SAML is not configured")
        # SAML redirect would go here
        # from onelogin.saml2.auth import OneLogin_Saml2_Auth
        raise HTTPException(status_code=501, detail="SAML login not yet implemented. Install python3-saml.")

    raise HTTPException(status_code=400, detail=f"Unknown SSO provider: {SSO_PROVIDER}")


@router.get("/oidc/callback")
async def oidc_callback(code: str, state: str = None):
    """Handle OIDC callback after IdP authentication."""
    if not SSO_ENABLED or SSO_PROVIDER != "oidc":
        raise HTTPException(status_code=400, detail="OIDC SSO is not enabled")

    # Exchange code for user info
    userinfo = await _oidc.exchange_code(code)
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email returned from OIDC provider")

    # Find or create user
    user = _find_or_create_sso_user(email, userinfo.get("name"))

    # Create JWT
    from .service import create_access_token, JWT_EXPIRE_MINUTES
    from . import db as auth_db

    auth_db.update_last_login(user["id"])
    token = create_access_token({"sub": user["id"], "username": user["username"], "role": user.get("role_id", "")})

    auth_db.log_audit(user["id"], user["username"], "sso_login",
                      details=f"OIDC login from {email}")

    # Redirect to frontend with token (frontend extracts from URL fragment)
    return RedirectResponse(f"/web/warranty.html#sso_token={token}")


@router.post("/saml/callback")
async def saml_callback(request: Request):
    """Handle SAML ACS callback."""
    if not SSO_ENABLED or SSO_PROVIDER != "saml":
        raise HTTPException(status_code=400, detail="SAML SSO is not enabled")

    # SAML processing would go here
    # from onelogin.saml2.auth import OneLogin_Saml2_Auth
    raise HTTPException(status_code=501, detail="SAML callback not yet implemented. Install python3-saml.")
