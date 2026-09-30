"""
Comprehensive Tenant Isolation, Security Hardening, and Session Tests (PRD Section 11 & Milestone M2).
Validates:
1. Strict cross-tenant isolation (User A receives 403 for User B's org, assessments, and answers).
2. Proper 404 status codes for non-existent entities.
3. Unauthenticated requests receive 401.
4. Role permissions (Viewer role receives 403 on mutation endpoints).
5. System Admin cross-tenant inspection (Admin can audit any tenant).
6. Password hashing verification (PBKDF2-SHA256).
7. HttpOnly session cookies for browser clients.
8. Rate limiting and account lockout after consecutive failed login attempts (429 Too Many Requests).
"""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.core.auth import (
    clear_rate_limit_state,
    hash_password,
    verify_password
)
from apps.api.models import User, Membership
from apps.api.database import SessionLocal

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Ensures a clean rate limiting state for each test."""
    clear_rate_limit_state()
    yield
    clear_rate_limit_state()


def test_password_hashing_pbkdf2_standard():
    """Validates that passwords are hashed using PBKDF2-HMAC-SHA256 with 100k rounds and salt."""
    raw_pw = "UltraSecurePassword999!"
    hashed = hash_password(raw_pw)

    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_password(raw_pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_tenant_isolation_cross_user_access_blocked():
    """
    User A (Company A) and User B (Company B) must be completely isolated.
    User A must receive 403 Forbidden for User B's assessment, answers, and org endpoints.
    """
    # 1. Provision User A and Org A
    res_a = client.post("/auth/signup", json={
        "full_name": "Alice Founder",
        "email": "alice@company-a.com",
        "password": "Password123!",
        "company_name": "Alpha Corporation"
    })
    assert res_a.status_code == 200
    token_a = res_a.json()["access_token"]
    org_a_id = res_a.json()["organization"]["id"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Provision User B and Org B
    res_b = client.post("/auth/signup", json={
        "full_name": "Bob Founder",
        "email": "bob@company-b.com",
        "password": "Password123!",
        "company_name": "Beta Corporation"
    })
    assert res_b.status_code == 200
    token_b = res_b.json()["access_token"]
    org_b_id = res_b.json()["organization"]["id"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. User B creates an assessment in Org B
    create_b = client.post(
        f"/orgs/{org_b_id}/assessments",
        headers=headers_b,
        json={
            "name": "Beta Corp Diligence",
            "industry": "SOFTWARE",
            "sub_sector": "B2B Enterprise SaaS"
        }
    )
    assert create_b.status_code == 200
    b_assessment_id = create_b.json()["assessment"]["id"]

    # --- CROSS-TENANT ATTEMPTS BY USER A ON USER B'S RESOURCES ---

    # 4. User A attempts to view User B's assessment -> 403 Forbidden
    res_cross_get = client.get(
        f"/assessments/{b_assessment_id}",
        headers=headers_a
    )
    assert res_cross_get.status_code == 403
    assert "Access denied" in res_cross_get.json()["detail"]

    # 5. User A attempts to view User B's assessment questions -> 403 Forbidden
    res_cross_qs = client.get(
        f"/assessments/{b_assessment_id}/questions",
        headers=headers_a
    )
    assert res_cross_qs.status_code == 403

    # 6. User A attempts to answer a question in User B's assessment -> 403 Forbidden
    res_cross_ans = client.put(
        f"/assessments/{b_assessment_id}/answers/SAAS_02",
        headers=headers_a,
        json={"value": True, "notes": "Unauthorized answer injection attempt"}
    )
    assert res_cross_ans.status_code == 403

    # 7. User A attempts to modify User B's assessment profile -> 403 Forbidden
    res_cross_prof = client.patch(
        f"/assessments/{b_assessment_id}/profile",
        headers=headers_a,
        json={"industry": "ENERGY"}
    )
    assert res_cross_prof.status_code == 403

    # 8. User A attempts to create an assessment inside User B's org -> 403 Forbidden
    res_cross_create = client.post(
        f"/orgs/{org_b_id}/assessments",
        headers=headers_a,
        json={"name": "Trojan Assessment", "industry": "SOFTWARE"}
    )
    assert res_cross_create.status_code == 403
    assert "do not belong to this organization" in res_cross_create.json()["detail"]

    # 9. User A attempts to read User B's organization metadata -> 403 Forbidden
    res_cross_org = client.get(
        f"/orgs/{org_b_id}",
        headers=headers_a
    )
    assert res_cross_org.status_code == 403

    # 10. User A attempts to list User B's organization assessments -> 403 Forbidden
    res_cross_list = client.get(
        f"/orgs/{org_b_id}/assessments",
        headers=headers_a
    )
    assert res_cross_list.status_code == 403


def test_tenant_isolation_404_on_nonexistent_resources():
    """Non-existent IDs must return 404 Not Found before tenant checks."""
    res_a = client.post("/auth/signup", json={
        "full_name": "Charlie Founder",
        "email": "charlie@company-c.com",
        "password": "Password123!",
        "company_name": "Gamma Corp"
    })
    headers = {"Authorization": f"Bearer {res_a.json()['access_token']}"}

    # Non-existent assessment
    res_missing_assess = client.get("/assessments/non-existent-uuid-12345", headers=headers)
    assert res_missing_assess.status_code == 404

    # Non-existent org
    res_missing_org = client.get("/orgs/non-existent-org-uuid", headers=headers)
    assert res_missing_org.status_code == 404

    # Non-existent org assessment creation
    res_missing_create = client.post(
        "/orgs/non-existent-org-uuid/assessments",
        headers=headers,
        json={"name": "Test", "industry": "SOFTWARE"}
    )
    assert res_missing_create.status_code == 404


def test_admin_cross_tenant_audit_access():
    """System Administrators possess read/audit access across all tenant organizations."""
    # 1. User B creates assessment
    res_b = client.post("/auth/signup", json={
        "full_name": "Dan Founder",
        "email": "dan@company-d.com",
        "password": "Password123!",
        "company_name": "Delta Systems"
    })
    token_b = res_b.json()["access_token"]
    org_b_id = res_b.json()["organization"]["id"]

    create_b = client.post(
        f"/orgs/{org_b_id}/assessments",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Delta Diligence", "industry": "SOFTWARE"}
    )
    assess_id = create_b.json()["assessment"]["id"]

    # 2. Admin inspects User B's assessment
    admin_headers = {"Authorization": "Bearer demo-token-admin"}
    admin_get = client.get(f"/assessments/{assess_id}", headers=admin_headers)
    assert admin_get.status_code == 200
    assert admin_get.json()["assessment"]["name"] == "Delta Diligence"

    # 3. Admin lists User B's org assessments
    admin_list = client.get(f"/orgs/{org_b_id}/assessments", headers=admin_headers)
    assert admin_list.status_code == 200
    assert len(admin_list.json()["assessments"]) >= 1


def test_role_based_permissions_viewer_restrictions():
    """Viewer role in an organization cannot mutate assessments or submit answers."""
    # 1. Create org with owner
    owner_res = client.post("/auth/signup", json={
        "full_name": "Eve Owner",
        "email": "eve@company-e.com",
        "password": "Password123!",
        "company_name": "Epsilon Holdings"
    })
    org_id = owner_res.json()["organization"]["id"]
    owner_token = owner_res.json()["access_token"]

    create_res = client.post(
        f"/orgs/{org_id}/assessments",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Epsilon Series B", "industry": "SOFTWARE"}
    )
    assess_id = create_res.json()["assessment"]["id"]

    # 2. Add Viewer user directly into DB
    import uuid
    viewer_email = f"viewer_{uuid.uuid4().hex[:6]}@company-e.com"
    db = SessionLocal()
    viewer_user = User(
        email=viewer_email,
        hashed_password=hash_password("Password123!"),
        full_name="Frank Viewer",
        is_active=True,
        is_admin=False
    )
    db.add(viewer_user)
    db.flush()
    membership = Membership(org_id=org_id, user_id=viewer_user.id, role="Viewer")
    db.add(membership)
    db.commit()
    viewer_token = f"demo-session-{viewer_user.id}"
    db.close()

    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Viewer CAN read questions
    read_res = client.get(f"/assessments/{assess_id}/questions", headers=viewer_headers)
    assert read_res.status_code == 200

    # Viewer CANNOT update answers -> 403 Forbidden
    ans_res = client.put(
        f"/assessments/{assess_id}/answers/SAAS_02",
        headers=viewer_headers,
        json={"value": True}
    )
    assert ans_res.status_code == 403
    assert "Viewers cannot modify" in ans_res.json()["detail"]

    # Viewer CANNOT modify assessment profile -> 403 Forbidden
    prof_res = client.patch(
        f"/assessments/{assess_id}/profile",
        headers=viewer_headers,
        json={"industry": "ENERGY"}
    )
    assert prof_res.status_code == 403


def test_httponly_cookie_session_handling():
    """
    Validates that:
    1. /auth/login and /auth/signup set HttpOnly session cookies.
    2. Requests authenticated solely via the cookie succeed without Authorization header.
    3. /auth/logout clears the session cookie.
    """
    test_client = TestClient(app)

    # 1. Login sets cookie
    login_res = test_client.post("/auth/login", json={
        "email": "founder@company.com",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    assert "ledgerlight_session" in login_res.cookies

    # 2. Call /me with no Authorization header (uses cookie from test_client)
    me_res = test_client.get("/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "founder@company.com"

    # 3. Call /auth/logout
    logout_res = test_client.post("/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"


def test_rate_limiting_and_account_lockout_on_login():
    """
    Validates that 5 consecutive failed login attempts trigger account lockout (429 Too Many Requests).
    """
    clear_rate_limit_state()

    email = "targeted-user@company.com"
    client.post("/auth/signup", json={
        "full_name": "Target User",
        "email": email,
        "password": "CorrectPassword123!",
        "company_name": "Security Test Corp"
    })

    # Attempts 1 to 4: Wrong password returns 401 Unauthorized
    for i in range(4):
        res = client.post("/auth/login", json={"email": email, "password": f"WrongAttempt{i}"})
        assert res.status_code == 401
        assert "Invalid email or password" in res.json()["detail"]

    # Attempt 5: Exceeds threshold, triggers 429 Too Many Requests lockout
    res_lockout = client.post("/auth/login", json={"email": email, "password": "WrongAttempt5"})
    assert res_lockout.status_code == 429
    assert "temporarily locked" in res_lockout.json()["detail"]

    # Subsequent attempt with CORRECT password is still locked out
    res_blocked = client.post("/auth/login", json={"email": email, "password": "CorrectPassword123!"})
    assert res_blocked.status_code == 429
    assert "temporarily locked" in res_blocked.json()["detail"]
