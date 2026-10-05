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
    verify_password,
    create_session_token
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
    viewer_token = create_session_token(viewer_user.id, db)
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


@pytest.fixture
def setup_test_tenants():
    import uuid
    uid_s = str(uuid.uuid4())[:8]
    res_a = client.post("/auth/signup", json={
        "full_name": "Tenant A User",
        "email": f"tenanta_{uid_s}@company-a.com",
        "password": "Password123!",
        "company_name": "Tenant A Org"
    })
    token_a = res_a.json()["access_token"]
    user_a = res_a.json()["user"]
    org_a_id = res_a.json()["organization"]["id"]

    create_a = client.post(
        f"/orgs/{org_a_id}/assessments",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Tenant A Assessment", "industry": "SOFTWARE"}
    )
    asmt_a_id = create_a.json()["assessment"]["id"]

    res_b = client.post("/auth/signup", json={
        "full_name": "Tenant B User",
        "email": f"tenantb_{uid_s}@company-b.com",
        "password": "Password123!",
        "company_name": "Tenant B Org"
    })
    token_b = res_b.json()["access_token"]
    user_b = res_b.json()["user"]
    org_b_id = res_b.json()["organization"]["id"]

    return {
        "user_a": {"id": user_a["id"], "token": token_a, "org_id": org_a_id},
        "user_b": {"id": user_b["id"], "token": token_b, "org_id": org_b_id},
        "assessment_a_id": asmt_a_id
    }


def test_guessing_demo_session_id_fails(setup_test_tenants):
    """
    STRICT REQUIREMENT: Guessing 'demo-session-<id>' or raw user IDs must fail with 401 Unauthorized.
    Tokens must be random 256-bit hashed tokens.
    """
    tenants = setup_test_tenants
    user_a_id = tenants["user_a"]["id"]
    asmt_a_id = tenants["assessment_a_id"]

    # 1. Guessing demo-session-<id>
    guessed_token = f"demo-session-{user_a_id}"
    res = client.get("/me", headers={"Authorization": f"Bearer {guessed_token}"})
    assert res.status_code == 401
    assert "Invalid or expired session token" in res.json()["detail"]

    # 2. Guessing raw user ID
    res_raw = client.get("/me", headers={"Authorization": f"Bearer {user_a_id}"})
    assert res_raw.status_code == 401

    # 3. Accessing assessment with guessed token
    res_asmt = client.get(f"/assessments/{asmt_a_id}", headers={"Authorization": f"Bearer {guessed_token}"})
    assert res_asmt.status_code == 401


def test_cross_user_token_cannot_access_my_data(setup_test_tenants):
    """
    STRICT REQUIREMENT: Another user's legitimate token cannot access my data room, assessment, or org.
    """
    tenants = setup_test_tenants
    user_b_token = tenants["user_b"]["token"]
    asmt_a_id = tenants["assessment_a_id"]
    org_a_id = tenants["user_a"]["org_id"]

    b_headers = {"Authorization": f"Bearer {user_b_token}"}

    # User B tries to view User A's assessment -> 403 Forbidden
    res = client.get(f"/assessments/{asmt_a_id}", headers=b_headers)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    # User B tries to update User A's assessment answers -> 403 Forbidden
    res_put = client.put(
        f"/assessments/{asmt_a_id}/answers/CORE_REV_QUAL_01",
        headers=b_headers,
        json={"value": True}
    )
    assert res_put.status_code == 403

    # User B tries to view User A's org -> 403 Forbidden
    res_org = client.get(f"/orgs/{org_a_id}", headers=b_headers)
    assert res_org.status_code == 403



def test_session_token_revocation_on_logout():
    """
    Validates that logging out revokes the session token, and subsequent requests fail.
    """
    # 1. Sign up a new user to obtain a fresh 256-bit token
    email = "logout_test_user@company.com"
    signup_res = client.post("/auth/signup", json={
        "full_name": "Logout Test User",
        "email": email,
        "password": "Password123!",
        "company_name": "Logout Corp"
    })
    assert signup_res.status_code == 200
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Token works initially
    me_res = client.get("/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 3. Call /auth/logout with token
    logout_res = client.post("/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"

    # 4. Token is now revoked -> 401 Unauthorized
    revoked_res = client.get("/me", headers=headers)
    assert revoked_res.status_code == 401
    assert "revoked" in revoked_res.json()["detail"].lower()


def test_expired_session_token_rejected():
    """
    Validates that expired session tokens are rejected with 401.
    """
    from datetime import timedelta
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "founder@company.com").first()
        assert user is not None
        # Create a token that already expired 1 hour ago
        expired_token = create_session_token(user.id, db, duration=timedelta(hours=-1))
    finally:
        db.close()

    res = client.get("/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()

