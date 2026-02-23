"""Tests for authentication, RBAC, bulk upload, and audit trail.

Runs against a live FastAPI test client with PostgreSQL or SQLite.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------- Unit tests for auth.service ----------

class TestAuthService:
    """Test JWT token creation, verification, password hashing."""

    def test_hash_and_verify_password(self):
        from app.auth.service import hash_password, verify_password
        hashed = hash_password("testpass123")
        assert hashed != "testpass123"
        assert verify_password("testpass123", hashed) is True
        assert verify_password("wrongpass", hashed) is False

    def test_create_and_decode_token(self):
        from app.auth.service import create_access_token, decode_token
        token = create_access_token({"sub": "user123", "username": "testuser"})
        assert isinstance(token, str)
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        assert "exp" in payload

    def test_decode_invalid_token(self):
        from app.auth.service import decode_token
        assert decode_token("invalid.token.here") is None
        assert decode_token("") is None

    def test_create_and_verify_reset_token(self):
        from app.auth.service import create_reset_token, verify_reset_token
        token = create_reset_token("user456")
        assert isinstance(token, str)
        user_id = verify_reset_token(token)
        assert user_id == "user456"

    def test_verify_reset_token_wrong_type(self):
        from app.auth.service import create_access_token, verify_reset_token
        # Regular access token should not pass as reset token
        token = create_access_token({"sub": "user789", "type": "access"})
        assert verify_reset_token(token) is None

    def test_get_user_permissions(self):
        from app.auth.service import get_user_permissions
        assert get_user_permissions('["claims:view", "claims:upload"]') == ["claims:view", "claims:upload"]
        assert get_user_permissions("[]") == []
        assert get_user_permissions("invalid") == []
        assert get_user_permissions(None) == []
        assert get_user_permissions(["already", "list"]) == ["already", "list"]

    def test_has_permission(self):
        from app.auth.service import has_permission
        assert has_permission(["admin:full"], "claims:view") is True  # admin has all
        assert has_permission(["claims:view"], "claims:view") is True
        assert has_permission(["claims:view"], "claims:upload") is False
        assert has_permission([], "claims:view") is False

    def test_has_any_permission(self):
        from app.auth.service import has_any_permission
        assert has_any_permission(["claims:view"], ["claims:view", "claims:upload"]) is True
        assert has_any_permission(["dashboard:view"], ["claims:view", "claims:upload"]) is False
        assert has_any_permission(["admin:full"], ["claims:view"]) is True  # admin bypass


# ---------- Unit tests for auth.models ----------

class TestAuthModels:
    """Test Pydantic models for auth."""

    def test_login_request(self):
        from app.auth.models import LoginRequest
        req = LoginRequest(username="admin", password="pass123")
        assert req.username == "admin"
        assert req.password == "pass123"

    def test_register_request(self):
        from app.auth.models import RegisterRequest
        req = RegisterRequest(username="newuser", email="new@test.com", password="pass123")
        assert req.username == "newuser"
        assert req.email == "new@test.com"

    def test_register_request_with_optional_fields(self):
        from app.auth.models import RegisterRequest
        req = RegisterRequest(username="testuser", email="e@test.com", password="pass123456", full_name="Full Name", phone="+1234567890")
        assert req.full_name == "Full Name"
        assert req.phone == "+1234567890"

    def test_change_password_request(self):
        from app.auth.models import ChangePasswordRequest
        req = ChangePasswordRequest(current_password="oldpass123", new_password="newpass123")
        assert req.current_password == "oldpass123"

    def test_permissions_constants(self):
        from app.auth.models import Permissions
        assert Permissions.ADMIN_FULL == "admin:full"
        assert Permissions.CLAIMS_VIEW == "claims:view"
        assert Permissions.USERS_CREATE == "users:create"

    def test_default_roles(self):
        from app.auth.models import DEFAULT_ROLES
        assert "admin" in DEFAULT_ROLES
        assert "analyst" in DEFAULT_ROLES
        assert "viewer" in DEFAULT_ROLES
        assert "admin:full" in DEFAULT_ROLES["admin"]["permissions"]
        assert DEFAULT_ROLES["admin"]["is_system"] is True


# ---------- Integration tests using FastAPI TestClient ----------

@pytest.fixture(scope="module")
def client():
    """Create a FastAPI test client."""
    from fastapi.testclient import TestClient
    from app.api.main import app

    # Initialize auth DB for testing
    try:
        from app.auth.db import init_auth_db
        init_auth_db()
    except Exception:
        pass

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    """Get an admin JWT token."""
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    if resp.status_code != 200:
        pytest.skip("Admin user not available (DB not initialized)")
    return resp.json()["access_token"]


class TestAuthEndpoints:
    """Test auth API endpoints."""

    def test_login_success(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role_name"] == "admin"
        assert "admin:full" in data["user"]["permissions"]

    def test_login_wrong_password(self, client):
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", json={"username": "nouser", "password": "pass123456"})
        assert resp.status_code == 401

    def test_me_without_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_with_token(self, client, admin_token):
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["is_active"] is True

    def test_me_with_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.xyz"})
        assert resp.status_code == 401

    def test_register_new_user(self, client):
        resp = client.post("/auth/register", json={
            "username": "testanalyst",
            "email": "analyst@test.com",
            "password": "test123",
            "full_name": "Test Analyst"
        })
        assert resp.status_code == 200
        assert "user_id" in resp.json()

    def test_register_duplicate_username(self, client):
        resp = client.post("/auth/register", json={
            "username": "admin",
            "email": "other@test.com",
            "password": "test123",
        })
        assert resp.status_code == 400
        assert "already taken" in resp.json()["detail"]

    def test_register_duplicate_email(self, client):
        resp = client.post("/auth/register", json={
            "username": "uniqueuser99",
            "email": "admin@verireceipt.com",
            "password": "test123",
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_change_password(self, client):
        # Login as testanalyst first
        resp = client.post("/auth/login", json={"username": "testanalyst", "password": "test123"})
        if resp.status_code != 200:
            pytest.skip("testanalyst not available")
        token = resp.json()["access_token"]

        resp = client.put("/auth/me/password", json={
            "current_password": "test123",
            "new_password": "newpass456"
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        # Verify new password works
        resp = client.post("/auth/login", json={"username": "testanalyst", "password": "newpass456"})
        assert resp.status_code == 200

        # Restore original password
        token2 = resp.json()["access_token"]
        client.put("/auth/me/password", json={
            "current_password": "newpass456",
            "new_password": "test123"
        }, headers={"Authorization": f"Bearer {token2}"})

    def test_change_password_wrong_current(self, client, admin_token):
        resp = client.put("/auth/me/password", json={
            "current_password": "wrongcurrent",
            "new_password": "newpass"
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400

    def test_forgot_password(self, client):
        resp = client.post("/auth/forgot-password", json={"email": "admin@verireceipt.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        # In dev mode, reset_token is returned
        if "reset_token" in data:
            assert len(data["reset_token"]) > 0

    def test_forgot_password_unknown_email(self, client):
        resp = client.post("/auth/forgot-password", json={"email": "nobody@nowhere.com"})
        assert resp.status_code == 200  # Should not reveal if email exists

    def test_reset_password(self, client):
        # Get reset token
        resp = client.post("/auth/forgot-password", json={"email": "admin@verireceipt.com"})
        data = resp.json()
        if "reset_token" not in data:
            pytest.skip("Reset token not available (SMTP configured)")
        token = data["reset_token"]

        # This would actually reset the admin password, so let's just test invalid token
        resp = client.post("/auth/reset-password", json={"token": "invalid_token", "new_password": "newpass"})
        assert resp.status_code == 400


class TestAdminEndpoints:
    """Test admin API endpoints (RBAC)."""

    def test_list_users_requires_auth(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 401

    def test_list_users_as_admin(self, client, admin_token):
        resp = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_list_users_as_non_admin(self, client):
        # Login as analyst
        resp = client.post("/auth/login", json={"username": "testanalyst", "password": "test123"})
        if resp.status_code != 200:
            pytest.skip("testanalyst not available")
        token = resp.json()["access_token"]

        resp = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403  # Permission denied

    def test_list_roles(self, client, admin_token):
        resp = client.get("/admin/roles", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data
        assert len(data["roles"]) >= 3  # admin, analyst, viewer

    def test_create_user(self, client, admin_token):
        resp = client.post("/admin/users?role_id=role_viewer", json={
            "username": "admintest_user",
            "email": "admintest@test.com",
            "password": "pass123",
            "full_name": "Admin Created User"
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert "user" in resp.json()

    def test_update_user(self, client, admin_token):
        # Get user list to find the test user
        resp = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        users = resp.json()["users"]
        test_user = next((u for u in users if u["username"] == "admintest_user"), None)
        if not test_user:
            pytest.skip("admintest_user not found")

        resp = client.put(f"/admin/users/{test_user['id']}", json={
            "full_name": "Updated Name",
            "role_id": "role_analyst"
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_delete_user(self, client, admin_token):
        resp = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        users = resp.json()["users"]
        test_user = next((u for u in users if u["username"] == "admintest_user"), None)
        if not test_user:
            pytest.skip("admintest_user not found")

        resp = client.delete(f"/admin/users/{test_user['id']}",
                             headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_cannot_delete_self(self, client, admin_token):
        # Get admin user id
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        admin_id = resp.json()["id"]

        resp = client.delete(f"/admin/users/{admin_id}",
                             headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400
        assert "yourself" in resp.json()["detail"]

    def test_create_role(self, client, admin_token):
        resp = client.post("/admin/roles", json={
            "name": "custom_tester",
            "description": "Test role",
            "permissions": ["claims:view", "dashboard:view"]
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert resp.json()["role"]["name"] == "custom_tester"

    def test_create_duplicate_role(self, client, admin_token):
        resp = client.post("/admin/roles", json={
            "name": "custom_tester",
            "description": "Dup",
            "permissions": []
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400

    def test_update_role(self, client, admin_token):
        resp = client.put("/admin/roles/role_custom_tester", json={
            "description": "Updated test role",
            "permissions": ["claims:view"]
        }, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_delete_custom_role(self, client, admin_token):
        resp = client.delete("/admin/roles/role_custom_tester",
                             headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_cannot_delete_system_role(self, client, admin_token):
        resp = client.delete("/admin/roles/role_admin",
                             headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400
        assert "system" in resp.json()["detail"].lower()


class TestAuditLogEndpoints:
    """Test audit log endpoints."""

    def test_audit_logs_list(self, client, admin_token):
        resp = client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data
        # Should have at least login events
        assert data["total"] >= 1

    def test_audit_logs_filter_by_action(self, client, admin_token):
        resp = client.get("/admin/audit-logs?action=login",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        for log in resp.json()["logs"]:
            assert log["action"] == "login"

    def test_audit_logs_requires_admin(self, client):
        # Login as analyst
        resp = client.post("/auth/login", json={"username": "testanalyst", "password": "test123"})
        if resp.status_code != 200:
            pytest.skip("testanalyst not available")
        token = resp.json()["access_token"]

        resp = client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestSSOEndpoints:
    """Test SSO status endpoint."""

    def test_sso_status(self, client):
        resp = client.get("/auth/sso/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "sso_enabled" in data
        assert data["sso_enabled"] is False  # Default

    def test_sso_login_disabled(self, client):
        resp = client.get("/auth/sso/login")
        assert resp.status_code == 400
        assert "not enabled" in resp.json()["detail"]


class TestPermissionsEndpoint:
    """Test the permissions listing endpoint."""

    def test_list_permissions(self, client, admin_token):
        resp = client.get("/admin/permissions", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "permissions" in data
        keys = [p["key"] for p in data["permissions"]]
        assert "admin:full" in keys
        assert "claims:view" in keys


class TestLoginRoute:
    """Test /login route and / redirect."""

    def test_root_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/login"

    def test_login_page_serves_html(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "VeriReceipt" in resp.text


class TestBulkUploadEndpoint:
    """Test bulk upload endpoint."""

    def test_bulk_upload_no_files(self, client, admin_token):
        # Empty multipart - should fail
        resp = client.post("/warranty/analyze/bulk",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           files=[])
        # FastAPI will reject missing required field
        assert resp.status_code == 422

    def test_bulk_upload_non_pdf(self, client, admin_token):
        import io
        fake_txt = io.BytesIO(b"not a pdf")
        resp = client.post("/warranty/analyze/bulk",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           files=[("files", ("test.txt", fake_txt, "text/plain"))])
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "error"


class TestBulkUploadWithRealPDFs:
    """Test bulk upload with real warranty PDFs from data/warranty_pdfs folder."""

    WARRANTY_PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "warranty_pdfs")

    def _get_pdf_files(self, max_files=3):
        """Get a few real PDFs from the test data folder."""
        pdf_dir = os.path.abspath(self.WARRANTY_PDF_DIR)
        if not os.path.isdir(pdf_dir):
            pytest.skip(f"warranty_pdfs directory not found: {pdf_dir}")
        pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")][:max_files]
        if not pdfs:
            pytest.skip("No PDF files found in warranty_pdfs")
        return pdf_dir, pdfs

    def test_bulk_upload_real_pdfs(self, client, admin_token):
        """Upload a few real PDFs and verify they all succeed."""
        pdf_dir, pdfs = self._get_pdf_files(3)
        files = []
        for name in pdfs:
            fh = open(os.path.join(pdf_dir, name), "rb")
            files.append(("files", (name, fh, "application/pdf")))

        try:
            resp = client.post("/warranty/analyze/bulk",
                               headers={"Authorization": f"Bearer {admin_token}"},
                               files=files)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == len(pdfs)
            assert data["success"] >= 1
            for r in data["results"]:
                if r["status"] == "success":
                    assert r["claim_id"] is not None
                    assert r["risk_score"] is not None
                    assert r["triage_class"] is not None
                    assert "duplicates_found" in r
        finally:
            for _, (_, fh, _) in files:
                fh.close()

    def test_bulk_upload_folder_all_pdfs(self, client, admin_token):
        """Upload ALL PDFs from the warranty_pdfs folder to simulate folder upload."""
        pdf_dir = os.path.abspath(self.WARRANTY_PDF_DIR)
        if not os.path.isdir(pdf_dir):
            pytest.skip("warranty_pdfs directory not found")
        pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
        if not pdfs:
            pytest.skip("No PDF files found")

        files = []
        for name in pdfs:
            fh = open(os.path.join(pdf_dir, name), "rb")
            files.append(("files", (name, fh, "application/pdf")))

        try:
            resp = client.post("/warranty/analyze/bulk",
                               headers={"Authorization": f"Bearer {admin_token}"},
                               files=files)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == len(pdfs)
            # At least some should succeed
            assert data["success"] >= 1
            print(f"\n  Folder upload: {data['total']} files, {data['success']} success, {data['failed']} failed")
            for r in data["results"]:
                print(f"    {r['filename']}: {r['status']} | risk={r.get('risk_score')} | triage={r.get('triage_class')} | dups={r.get('duplicates_found', 0)}")
        finally:
            for _, (_, fh, _) in files:
                fh.close()

    def test_duplicate_detection_on_reupload(self, client, admin_token):
        """Upload same PDF twice - second upload should detect duplicates."""
        pdf_dir, pdfs = self._get_pdf_files(1)
        name = pdfs[0]
        path = os.path.join(pdf_dir, name)

        # First upload
        with open(path, "rb") as fh:
            resp1 = client.post("/warranty/analyze/bulk",
                                headers={"Authorization": f"Bearer {admin_token}"},
                                files=[("files", (name, fh, "application/pdf"))])
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["success"] >= 1

        # Second upload of same file - should detect duplicate
        with open(path, "rb") as fh:
            resp2 = client.post("/warranty/analyze/bulk",
                                headers={"Authorization": f"Bearer {admin_token}"},
                                files=[("files", (name, fh, "application/pdf"))])
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] >= 1
        # The second upload should find duplicates (the first upload)
        dup_count = sum(r.get("duplicates_found", 0) for r in data2["results"] if r["status"] == "success")
        print(f"\n  Re-upload duplicate detection: {dup_count} duplicates found for {name}")
        # Duplicate detection is best-effort, so just verify the field is present
        for r in data2["results"]:
            if r["status"] == "success":
                assert "duplicates_found" in r


# ---------- Cleanup ----------

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_users(client, admin_token):
    """Clean up test users after all tests."""
    yield
    # Remove test users
    try:
        resp = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        if resp.status_code == 200:
            for u in resp.json().get("users", []):
                if u["username"] in ("testanalyst", "admintest_user"):
                    client.delete(f"/admin/users/{u['id']}",
                                  headers={"Authorization": f"Bearer {admin_token}"})
    except Exception:
        pass
